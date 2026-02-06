use anyhow::{Context, Result};
use chrono::{DateTime, Local, TimeZone, Utc};
use crossterm::{
    event::{self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, List, ListItem, ListState, Paragraph, Tabs},
    Frame, Terminal,
};
use rss::Channel;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::io;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

const REFRESH_INTERVAL: u64 = 120; // seconds

#[derive(Debug, Clone, Serialize, Deserialize)]
struct FeedEntry {
    id: i64,
    #[serde(rename = "sourceName")]
    source_name: String,
    #[serde(rename = "pubDate")]
    pub_date: String,
    timestamp: i64,
    url: String,
    title: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct CachedFeed {
    entries: Vec<FeedEntry>,
    created_at: i64,
}

#[derive(Debug, Clone, Deserialize)]
struct FeedCategory {
    title: String,
    feeds: HashMap<String, String>,
    #[serde(default)]
    show_author: bool,
}

type FeedsConfig = HashMap<String, FeedCategory>;

#[derive(Clone)]
struct LoadingState {
    is_loading: bool,
    current: usize,
    total: usize,
    category: String,
}

struct App {
    categories: Vec<String>,
    category_titles: HashMap<String, String>,
    feeds_config: FeedsConfig,
    current_category: usize,
    entries: HashMap<String, Vec<FeedEntry>>,
    list_state: ListState,
    data_path: PathBuf,
    last_refresh: Instant,
    error_message: Option<String>,
    loading_state: Arc<Mutex<LoadingState>>,
}

impl App {
    fn new() -> Result<Self> {
        let data_path = dirs::home_dir()
            .context("Could not find home directory")?
            .join(".rreader");

        fs::create_dir_all(&data_path)?;

        let feeds_path = data_path.join("feeds.json");

        // Copy default feeds.json if not exists
        if !feeds_path.exists() {
            let default_feeds = include_str!("../feeds.json");
            fs::write(&feeds_path, default_feeds)?;
        }

        let feeds_content = fs::read_to_string(&feeds_path)?;
        let feeds_config: FeedsConfig = serde_json::from_str(&feeds_content)?;

        let mut categories: Vec<String> = feeds_config.keys().cloned().collect();
        categories.sort(); // Consistent ordering

        let category_titles: HashMap<String, String> = feeds_config
            .iter()
            .map(|(k, v)| (k.clone(), v.title.clone()))
            .collect();

        let mut list_state = ListState::default();
        list_state.select(Some(0));

        let loading_state = Arc::new(Mutex::new(LoadingState {
            is_loading: false,
            current: 0,
            total: 0,
            category: String::new(),
        }));

        Ok(App {
            categories,
            category_titles,
            feeds_config,
            current_category: 0,
            entries: HashMap::new(),
            list_state,
            data_path,
            last_refresh: Instant::now() - Duration::from_secs(REFRESH_INTERVAL + 1),
            error_message: None,
            loading_state,
        })
    }

    fn current_category_name(&self) -> &str {
        &self.categories[self.current_category]
    }

    fn current_entries(&self) -> Vec<&FeedEntry> {
        self.entries
            .get(self.current_category_name())
            .map(|e| e.iter().collect())
            .unwrap_or_default()
    }

    fn load_cached_feed(&self, category: &str) -> Option<CachedFeed> {
        let cache_path = self.data_path.join(format!("rss_{}.json", category));
        if let Ok(content) = fs::read_to_string(&cache_path) {
            if let Ok(cached) = serde_json::from_str::<CachedFeed>(&content) {
                return Some(cached);
            }
        }
        None
    }

    fn save_cached_feed(&self, category: &str, feed: &CachedFeed) -> Result<()> {
        let cache_path = self.data_path.join(format!("rss_{}.json", category));
        let content = serde_json::to_string_pretty(feed)?;
        fs::write(&cache_path, content)?;
        Ok(())
    }

    fn fetch_feeds(&mut self, category: &str) -> Result<Vec<FeedEntry>> {
        let config = self.feeds_config.get(category).context("Category not found")?;
        let mut all_entries: HashMap<i64, FeedEntry> = HashMap::new();
        let mut errors: Vec<String> = Vec::new();

        let feeds: Vec<(String, String)> = config.feeds.iter()
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
        let total = feeds.len();
        let show_author = config.show_author;

        // Update loading state
        {
            let mut state = self.loading_state.lock().unwrap();
            state.is_loading = true;
            state.current = 0;
            state.total = total;
            state.category = category.to_string();
        }

        for (idx, (source_name, url)) in feeds.iter().enumerate() {
            // Update progress
            {
                let mut state = self.loading_state.lock().unwrap();
                state.current = idx + 1;
            }

            match Self::fetch_single_feed(source_name, url, show_author) {
                Ok(entries) => {
                    for entry in entries {
                        all_entries.insert(entry.id, entry);
                    }
                }
                Err(e) => {
                    errors.push(format!("{}: {}", source_name, e));
                }
            }
        }

        // Done loading
        {
            let mut state = self.loading_state.lock().unwrap();
            state.is_loading = false;
        }

        // Show error only if ALL feeds failed
        if !errors.is_empty() && all_entries.is_empty() {
            self.error_message = Some(errors.join("\n"));
        }

        let mut entries: Vec<FeedEntry> = all_entries.into_values().collect();
        entries.sort_by(|a, b| b.timestamp.cmp(&a.timestamp));

        if !entries.is_empty() {
            let cached = CachedFeed {
                entries: entries.clone(),
                created_at: Utc::now().timestamp(),
            };
            let _ = self.save_cached_feed(category, &cached);
        }

        Ok(entries)
    }

    fn fetch_single_feed(source_name: &str, url: &str, show_author: bool) -> Result<Vec<FeedEntry>> {
        let response = ureq::get(url)
            .set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            .timeout(Duration::from_secs(15))
            .call()?;

        let body = response.into_string()?;
        let channel = Channel::read_from(body.as_bytes())?;

        let mut entries = Vec::new();
        let today = Local::now().date_naive();

        for item in channel.items() {
            let title = item.title().unwrap_or("(No title)").to_string();
            let link = item.link().unwrap_or("").to_string();

            let pub_date = item.pub_date().unwrap_or("");
            let parsed_date = DateTime::parse_from_rfc2822(pub_date)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now());

            let local_date = Local.from_utc_datetime(&parsed_date.naive_utc());
            let timestamp = parsed_date.timestamp();

            let formatted_date = if local_date.date_naive() == today {
                local_date.format("%H:%M").to_string()
            } else {
                local_date.format("%b %d, %H:%M").to_string()
            };

            // Get author if show_author is enabled
            let display_name = if show_author {
                item.author()
                    .or_else(|| item.dublin_core_ext().and_then(|dc| dc.creators().first().map(|s| s.as_str())))
                    .unwrap_or(source_name)
                    .to_string()
            } else {
                source_name.to_string()
            };

            entries.push(FeedEntry {
                id: timestamp,
                source_name: display_name,
                pub_date: formatted_date,
                timestamp,
                url: link,
                title,
            });
        }

        Ok(entries)
    }

    fn refresh_current_category(&mut self) {
        let category = self.current_category_name().to_string();

        match self.fetch_feeds(&category) {
            Ok(entries) => {
                self.entries.insert(category.clone(), entries);
                self.last_refresh = Instant::now();
            }
            Err(e) => {
                self.error_message = Some(format!("Error: {}", e));
            }
        }
    }

    fn load_or_refresh(&mut self) {
        let category = self.current_category_name().to_string();

        // Try loading from cache first
        if let Some(cached) = self.load_cached_feed(&category) {
            let age = Utc::now().timestamp() - cached.created_at;
            if age < REFRESH_INTERVAL as i64 && !cached.entries.is_empty() {
                self.entries.insert(category.clone(), cached.entries);
                return;
            }
        }

        // Fetch fresh data
        self.refresh_current_category();
    }

    fn next_category(&mut self) {
        self.current_category = (self.current_category + 1) % self.categories.len();
        self.list_state.select(Some(0));
        self.load_or_refresh();
    }

    fn prev_category(&mut self) {
        if self.current_category == 0 {
            self.current_category = self.categories.len() - 1;
        } else {
            self.current_category -= 1;
        }
        self.list_state.select(Some(0));
        self.load_or_refresh();
    }

    fn next_item(&mut self) {
        let entries = self.current_entries();
        if entries.is_empty() {
            return;
        }
        let i = match self.list_state.selected() {
            Some(i) => (i + 1) % entries.len(),
            None => 0,
        };
        self.list_state.select(Some(i));
    }

    fn prev_item(&mut self) {
        let entries = self.current_entries();
        if entries.is_empty() {
            return;
        }
        let i = match self.list_state.selected() {
            Some(i) => {
                if i == 0 {
                    entries.len() - 1
                } else {
                    i - 1
                }
            }
            None => 0,
        };
        self.list_state.select(Some(i));
    }

    fn open_selected(&self) {
        let entries = self.current_entries();
        if let Some(i) = self.list_state.selected() {
            if let Some(entry) = entries.get(i) {
                let _ = open::that(&entry.url);
            }
        }
    }

    fn page_down(&mut self) {
        let entries = self.current_entries();
        if entries.is_empty() {
            return;
        }
        let i = match self.list_state.selected() {
            Some(i) => (i + 10).min(entries.len() - 1),
            None => 0,
        };
        self.list_state.select(Some(i));
    }

    fn page_up(&mut self) {
        let i = match self.list_state.selected() {
            Some(i) => i.saturating_sub(10),
            None => 0,
        };
        self.list_state.select(Some(i));
    }

    fn dismiss_error(&mut self) {
        self.error_message = None;
    }

    fn has_error(&self) -> bool {
        self.error_message.is_some()
    }

    fn get_loading_state(&self) -> LoadingState {
        self.loading_state.lock().unwrap().clone()
    }
}

fn centered_rect(percent_x: u16, percent_y: u16, r: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(r);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}

fn ui(f: &mut Frame, app: &mut App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(0),
        ])
        .split(f.size());

    // Tabs
    let titles: Vec<Line> = app
        .categories
        .iter()
        .map(|c| {
            let title = app.category_titles.get(c).unwrap_or(c);
            Line::from(title.as_str())
        })
        .collect();

    let tabs = Tabs::new(titles)
        .block(Block::default().borders(Borders::ALL).title(" rreader "))
        .select(app.current_category)
        .style(Style::default().fg(Color::White))
        .highlight_style(Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD));

    f.render_widget(tabs, chunks[0]);

    // Feed list
    let entries = app.current_entries();
    let category_name = app.current_category_name();
    let title = app.category_titles.get(category_name).unwrap_or(&category_name.to_string()).clone();

    if entries.is_empty() {
        // Show "No entries" message
        let loading_state = app.get_loading_state();
        let message = if loading_state.is_loading {
            "Loading...".to_string()
        } else {
            "No entries available. Press 'r' to refresh.".to_string()
        };

        let empty_msg = Paragraph::new(message)
            .alignment(Alignment::Center)
            .block(Block::default().borders(Borders::ALL).title(format!(" {} (0) ", title)));
        f.render_widget(empty_msg, chunks[1]);
    } else {
        let items: Vec<ListItem> = entries
            .iter()
            .enumerate()
            .map(|(i, entry)| {
                let source = format!("[{:^14}]", truncate_str(&entry.source_name, 14));
                let date = format!("{:>12}", entry.pub_date);
                let title = truncate_str(&entry.title, 80);

                let style = if Some(i) == app.list_state.selected() {
                    Style::default().fg(Color::Black).bg(Color::White)
                } else {
                    Style::default()
                };

                ListItem::new(Line::from(vec![
                    Span::styled(source, Style::default().fg(Color::Cyan)),
                    Span::raw(" "),
                    Span::styled(date, Style::default().fg(Color::DarkGray)),
                    Span::raw(" "),
                    Span::styled(title, style),
                ]))
            })
            .collect();

        let list = List::new(items)
            .block(Block::default().borders(Borders::ALL).title(format!(" {} ({}) ", title, entries.len())));

        f.render_stateful_widget(list, chunks[1], &mut app.list_state);
    }

    // Loading indicator (top-right corner)
    let loading_state = app.get_loading_state();
    if loading_state.is_loading {
        let loading_text = format!(" Loading... ({}/{}) ", loading_state.current, loading_state.total);
        let width = loading_text.len() as u16 + 2;
        let loading_area = Rect {
            x: f.size().width.saturating_sub(width + 1),
            y: 0,
            width,
            height: 1,
        };
        let loading_widget = Paragraph::new(loading_text)
            .style(Style::default().fg(Color::Black).bg(Color::Yellow));
        f.render_widget(loading_widget, loading_area);
    }

    // Error popup
    if let Some(ref error) = app.error_message {
        let area = centered_rect(60, 20, f.size());
        f.render_widget(Clear, area);

        let error_text = format!("{}\n\nPress any key to dismiss", error);
        let popup = Paragraph::new(error_text)
            .style(Style::default().fg(Color::White))
            .block(
                Block::default()
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(Color::Red))
                    .title(" Error ")
                    .title_style(Style::default().fg(Color::Red).add_modifier(Modifier::BOLD))
            );
        f.render_widget(popup, area);
    }
}

fn truncate_str(s: &str, max_len: usize) -> String {
    let chars: Vec<char> = s.chars().collect();
    if chars.len() <= max_len {
        s.to_string()
    } else {
        chars[..max_len - 3].iter().collect::<String>() + "..."
    }
}

fn main() -> Result<()> {
    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let mut app = App::new()?;
    app.load_or_refresh();

    let tick_rate = Duration::from_millis(100);
    let mut last_tick = Instant::now();

    loop {
        terminal.draw(|f| ui(f, &mut app))?;

        let timeout = tick_rate
            .checked_sub(last_tick.elapsed())
            .unwrap_or_else(|| Duration::from_secs(0));

        if crossterm::event::poll(timeout)? {
            if let Event::Key(key) = event::read()? {
                // If error popup is showing, dismiss on any key
                if app.has_error() {
                    app.dismiss_error();
                    continue;
                }

                match key.code {
                    KeyCode::Char('q') | KeyCode::Esc => break,
                    KeyCode::Char('c') if key.modifiers.contains(KeyModifiers::CONTROL) => break,
                    KeyCode::Tab => app.next_category(),
                    KeyCode::BackTab => app.prev_category(),
                    KeyCode::Down | KeyCode::Char('j') => app.next_item(),
                    KeyCode::Up | KeyCode::Char('k') => app.prev_item(),
                    KeyCode::PageDown | KeyCode::Char('d') if key.modifiers.contains(KeyModifiers::CONTROL) => app.page_down(),
                    KeyCode::PageUp | KeyCode::Char('u') if key.modifiers.contains(KeyModifiers::CONTROL) => app.page_up(),
                    KeyCode::Enter | KeyCode::Char('o') => app.open_selected(),
                    KeyCode::Char('r') => app.refresh_current_category(),
                    KeyCode::Char('1') => { app.current_category = 0.min(app.categories.len() - 1); app.list_state.select(Some(0)); app.load_or_refresh(); }
                    KeyCode::Char('2') => { app.current_category = 1.min(app.categories.len() - 1); app.list_state.select(Some(0)); app.load_or_refresh(); }
                    KeyCode::Char('3') => { app.current_category = 2.min(app.categories.len() - 1); app.list_state.select(Some(0)); app.load_or_refresh(); }
                    KeyCode::Char('4') => { app.current_category = 3.min(app.categories.len() - 1); app.list_state.select(Some(0)); app.load_or_refresh(); }
                    KeyCode::Char('g') => app.list_state.select(Some(0)),
                    KeyCode::Char('G') => {
                        let len = app.current_entries().len();
                        if len > 0 {
                            app.list_state.select(Some(len - 1));
                        }
                    }
                    _ => {}
                }
            }
        }

        if last_tick.elapsed() >= tick_rate {
            last_tick = Instant::now();

            // Auto-refresh check
            if app.last_refresh.elapsed() >= Duration::from_secs(REFRESH_INTERVAL) {
                let loading_state = app.get_loading_state();
                if !loading_state.is_loading {
                    app.refresh_current_category();
                }
            }
        }
    }

    // Restore terminal
    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        LeaveAlternateScreen,
        DisableMouseCapture
    )?;
    terminal.show_cursor()?;

    Ok(())
}
