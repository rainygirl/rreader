use anyhow::{Context, Result};
use chrono::{DateTime, Local, TimeZone, Utc};
use crossterm::{
    event::{self, Event, KeyCode, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{
    backend::CrosstermBackend,
    buffer::Buffer,
    style::{Color, Style},
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
use unicode_width::UnicodeWidthChar;

const REFRESH_INTERVAL: u64 = 120;
const MARQUEE_SPEED: f64 = 20.0;
const MARQUEE_SPEED_RETURN: f64 = 400.0;
const MARQUEE_DELAY: i32 = 40;
const MARQUEE_DELAY_RETURN: i32 = 120;
const SOURCE_COL: u16 = 1;
const TITLE_COL: u16 = 20;

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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    title_original: Option<String>,
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
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum MarqueeDirection {
    Left,
    Right,
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum InputMode {
    Normal,
    NumberJump,
}

#[derive(Debug, Clone)]
struct ColorScheme {
    default: Color,
    number: Color,
    numberselected: Color,
    source: Color,
    time: Color,
    selected_bg: Color,
    alertfg: Color,
    alertbg: Color,
    categoryfg: Color,
    categorybg: Color,
    categoryfg_s: Color,
    categorybg_s: Color,
}

impl ColorScheme {
    fn new_16() -> Self {
        ColorScheme {
            default: Color::White,
            number: Color::White,
            numberselected: Color::White,
            source: Color::Yellow,
            time: Color::DarkGray,
            selected_bg: Color::White,
            alertfg: Color::White,
            alertbg: Color::Blue,
            categoryfg: Color::Yellow,
            categorybg: Color::Black,
            categoryfg_s: Color::Black,
            categorybg_s: Color::Yellow,
        }
    }

    fn new_256() -> Self {
        ColorScheme {
            default: Color::Indexed(7),
            number: Color::Indexed(8),
            numberselected: Color::Indexed(15),
            source: Color::Indexed(2),
            time: Color::Indexed(8),
            selected_bg: Color::Indexed(15),
            alertfg: Color::Indexed(15),
            alertbg: Color::Indexed(12),
            categoryfg: Color::Indexed(223),
            categorybg: Color::Indexed(235),
            categoryfg_s: Color::Indexed(235),
            categorybg_s: Color::Indexed(223),
        }
    }
}

// ── Gemini API helpers ──

fn load_gemini_api_key() -> Option<String> {
    let config_path = dirs::home_dir()?.join(".rreader_gemini_config.json");
    if let Ok(content) = fs::read_to_string(&config_path) {
        if let Ok(config) = serde_json::from_str::<serde_json::Value>(&content) {
            return config
                .get("GEMINI_API_KEY")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string());
        }
    }
    None
}

fn load_translation_cache() -> HashMap<String, String> {
    let path = match dirs::home_dir() {
        Some(h) => h.join(".rreader_translation_cache.json"),
        None => return HashMap::new(),
    };
    if let Ok(content) = fs::read_to_string(&path) {
        if let Ok(cache) = serde_json::from_str::<HashMap<String, String>>(&content) {
            return cache;
        }
    }
    HashMap::new()
}

fn save_translation_cache(cache: &HashMap<String, String>) {
    let path = match dirs::home_dir() {
        Some(h) => h.join(".rreader_translation_cache.json"),
        None => return,
    };
    if let Ok(content) = serde_json::to_string_pretty(cache) {
        let _ = fs::write(&path, content);
    }
}

fn call_gemini_api(api_key: &str, prompt: &str) -> Result<String> {
    let url = format!(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={}",
        api_key
    );

    let body = serde_json::json!({
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }]
    });

    let response = ureq::post(&url)
        .set("Content-Type", "application/json")
        .timeout(Duration::from_secs(30))
        .send_string(&body.to_string())?;

    let resp_text = response.into_string()?;
    let resp_json: serde_json::Value = serde_json::from_str(&resp_text)?;

    let text = resp_json
        .get("candidates")
        .and_then(|c| c.get(0))
        .and_then(|c| c.get("content"))
        .and_then(|c| c.get("parts"))
        .and_then(|p| p.get(0))
        .and_then(|p| p.get("text"))
        .and_then(|t| t.as_str())
        .unwrap_or("")
        .to_string();

    Ok(text)
}

fn translate_titles_batch(
    titles: &[String],
    api_key: &str,
    cache: &mut HashMap<String, String>,
) -> HashMap<String, String> {
    let mut result = HashMap::new();
    let mut titles_to_translate = Vec::new();

    for t in titles {
        if let Some(cached) = cache.get(t) {
            result.insert(t.clone(), cached.clone());
        } else {
            titles_to_translate.push(t.clone());
        }
    }

    if titles_to_translate.is_empty() {
        return result;
    }

    let titles_json = serde_json::json!({ "titles": titles_to_translate });
    let prompt = format!(
        "Translate the 'titles' in the following JSON to Korean and return the result as a JSON object where each original title from the input is a key and its Korean translation is the value. For example, for input {{\"titles\": [\"Hello\", \"World\"]}}, the output should be {{\"Hello\": \"안녕하세요\", \"World\": \"세상\"}}. Respond with ONLY the JSON object.\n\nInput:\n{}",
        titles_json
    );

    if let Ok(response_text) = call_gemini_api(api_key, &prompt) {
        let cleaned = response_text
            .trim()
            .trim_start_matches("```json")
            .trim_start_matches("```")
            .trim_end_matches("```")
            .trim();

        if let Ok(translated_data) = serde_json::from_str::<serde_json::Value>(cleaned) {
            let dict = if let Some(titles_obj) = translated_data.get("titles") {
                titles_obj
            } else {
                &translated_data
            };

            if let Some(obj) = dict.as_object() {
                for (original, translated) in obj {
                    if let Some(t) = translated.as_str() {
                        cache.insert(original.clone(), t.to_string());
                        result.insert(original.clone(), t.to_string());
                    }
                }
            }
        }
    }

    result
}

// ── HTML tag stripping ──

fn strip_html_tags(html: &str) -> String {
    let mut result = String::with_capacity(html.len());
    let mut in_tag = false;
    let mut in_script = false;
    let mut in_style = false;
    let mut tag_name = String::new();
    let mut capturing_tag_name = false;

    for c in html.chars() {
        if c == '<' {
            in_tag = true;
            tag_name.clear();
            capturing_tag_name = true;
            continue;
        }
        if c == '>' {
            in_tag = false;
            let lower = tag_name.to_lowercase();
            if lower == "script" {
                in_script = true;
            } else if lower == "/script" {
                in_script = false;
            } else if lower == "style" {
                in_style = true;
            } else if lower == "/style" {
                in_style = false;
            } else if lower == "br" || lower == "br/" || lower == "p" || lower == "/p"
                || lower == "div" || lower == "/div" || lower == "li" || lower == "/li"
            {
                result.push('\n');
            }
            capturing_tag_name = false;
            continue;
        }
        if in_tag {
            if capturing_tag_name {
                if c.is_whitespace() || c == '/' && tag_name.is_empty() {
                    if !tag_name.is_empty() {
                        capturing_tag_name = false;
                    } else if c == '/' {
                        tag_name.push(c);
                    }
                } else {
                    tag_name.push(c);
                }
            }
            continue;
        }
        if in_script || in_style {
            continue;
        }
        result.push(c);
    }

    // Decode common HTML entities
    result
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .replace("&#x27;", "'")
        .replace("&nbsp;", " ")
        .replace("&#160;", " ")
}

fn summarize_with_gemini(url: &str, api_key: &str) -> String {
    // Fetch URL content
    let response = match ureq::get(url)
        .set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        .timeout(Duration::from_secs(10))
        .call()
    {
        Ok(r) => r,
        Err(e) => return format!("Error fetching URL: {}", e),
    };

    let body = match response.into_string() {
        Ok(b) => b,
        Err(e) => return format!("Error reading response: {}", e),
    };

    let page_text = strip_html_tags(&body);

    // Truncate if too long (Gemini has input limits)
    let truncated = if page_text.len() > 30000 {
        &page_text[..30000]
    } else {
        &page_text
    };

    let prompt = format!(
        "Please summarize the following text in Korean, extracted from the URL {}:\n\n{}",
        url, truncated
    );

    match call_gemini_api(api_key, &prompt) {
        Ok(text) => text,
        Err(e) => format!("Error from Gemini API: {}", e),
    }
}

fn wrap_text_for_display(text: &str, width: usize) -> Vec<String> {
    let mut lines = Vec::new();
    for line in text.lines() {
        if line.is_empty() {
            lines.push(String::new());
            continue;
        }
        let mut current = String::new();
        let mut current_width = 0;
        for c in line.chars() {
            let cw = UnicodeWidthChar::width(c).unwrap_or(0);
            if current_width + cw > width {
                lines.push(current);
                current = String::new();
                current_width = 0;
            }
            current.push(c);
            current_width += cw;
        }
        if !current.is_empty() {
            lines.push(current);
        }
    }
    lines
}

struct App {
    categories: Vec<String>,
    category_titles: HashMap<String, String>,
    feeds_config: FeedsConfig,
    current_category: usize,
    entries: HashMap<String, Vec<FeedEntry>>,
    selected: Option<usize>,
    data_path: PathBuf,
    last_refresh: Instant,
    loading_state: Arc<Mutex<LoadingState>>,
    // Marquee state
    marquee_shift: i32,
    marquee_direction: MarqueeDirection,
    marquee_tick_count: u64,
    // Input mode
    input_mode: InputMode,
    input_number: String,
    pre_input_selected: Option<usize>,
    // Help
    show_help: bool,
    // Colors
    colors: ColorScheme,
    // Terminal dimensions (cached per frame)
    terminal_width: u16,
    terminal_height: u16,
    // Gemini translation
    gemini_api_key: Option<String>,
    translating_in_progress: Arc<Mutex<bool>>,
    translation_cache: Arc<Mutex<HashMap<String, String>>>,
    needs_redraw: Arc<Mutex<bool>>,
    pending_translations: Arc<Mutex<HashMap<String, HashMap<String, String>>>>,
    // Summary modal
    show_modal: bool,
    modal_text: Vec<String>,
    modal_raw_text: String,
    modal_wrapped_width: u16,
    modal_scroll: usize,
    summarizing: bool,
    summarize_url: String,
}

impl App {
    fn new() -> Result<Self> {
        let data_path = dirs::home_dir()
            .context("Could not find home directory")?
            .join(".rreader");

        fs::create_dir_all(&data_path)?;

        let feeds_path = data_path.join("feeds.json");

        if !feeds_path.exists() {
            let default_feeds = include_str!("../feeds.json");
            fs::write(&feeds_path, default_feeds)?;
        }

        let feeds_content = fs::read_to_string(&feeds_path)?;
        let feeds_config: FeedsConfig = serde_json::from_str(&feeds_content)?;

        let mut categories: Vec<String> = feeds_config.keys().cloned().collect();
        categories.sort();

        let category_titles: HashMap<String, String> = feeds_config
            .iter()
            .map(|(k, v)| (k.clone(), v.title.clone()))
            .collect();

        let loading_state = Arc::new(Mutex::new(LoadingState {
            is_loading: false,
            current: 0,
            total: 0,
        }));

        let colors = if std::env::var("TERM")
            .unwrap_or_default()
            .contains("256")
        {
            ColorScheme::new_256()
        } else {
            ColorScheme::new_16()
        };

        let gemini_api_key = load_gemini_api_key();
        let cache = load_translation_cache();

        Ok(App {
            categories,
            category_titles,
            feeds_config,
            current_category: 0,
            entries: HashMap::new(),
            selected: None,
            data_path,
            last_refresh: Instant::now() - Duration::from_secs(REFRESH_INTERVAL + 1),
            loading_state,
            marquee_shift: 0,
            marquee_direction: MarqueeDirection::Left,
            marquee_tick_count: 0,
            input_mode: InputMode::Normal,
            input_number: String::new(),
            pre_input_selected: None,
            show_help: false,
            colors,
            terminal_width: 80,
            terminal_height: 24,
            gemini_api_key,
            translating_in_progress: Arc::new(Mutex::new(false)),
            translation_cache: Arc::new(Mutex::new(cache)),
            needs_redraw: Arc::new(Mutex::new(false)),
            pending_translations: Arc::new(Mutex::new(HashMap::new())),
            show_modal: false,
            modal_text: Vec::new(),
            modal_raw_text: String::new(),
            modal_wrapped_width: 0,
            modal_scroll: 0,
            summarizing: false,
            summarize_url: String::new(),
        })
    }

    fn current_category_name(&self) -> &str {
        &self.categories[self.current_category]
    }

    fn current_entries(&self) -> &[FeedEntry] {
        self.entries
            .get(self.current_category_name())
            .map(|e| e.as_slice())
            .unwrap_or(&[])
    }

    fn row_limit(&self) -> usize {
        let max_rows = (self.terminal_height as usize).saturating_sub(2);
        let entry_count = self.current_entries().len();
        entry_count.min(max_rows).min(999)
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
        let config = self
            .feeds_config
            .get(category)
            .context("Category not found")?;
        let mut all_entries: HashMap<i64, FeedEntry> = HashMap::new();

        let feeds: Vec<(String, String)> = config
            .feeds
            .iter()
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();
        let total = feeds.len();
        let show_author = config.show_author;

        {
            let mut state = self.loading_state.lock().unwrap();
            state.is_loading = true;
            state.current = 0;
            state.total = total;
        }

        for (idx, (source_name, url)) in feeds.iter().enumerate() {
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
                Err(_) => {}
            }
        }

        {
            let mut state = self.loading_state.lock().unwrap();
            state.is_loading = false;
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

    fn fetch_single_feed(
        source_name: &str,
        url: &str,
        show_author: bool,
    ) -> Result<Vec<FeedEntry>> {
        let response = ureq::get(url)
            .set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
            .timeout(Duration::from_secs(15))
            .call()?;

        let body = response.into_string()?;

        // Try RSS first, then Atom
        if let Ok(channel) = Channel::read_from(body.as_bytes()) {
            Self::parse_rss_channel(&channel, source_name, show_author)
        } else if let Ok(feed) = body.parse::<atom_syndication::Feed>() {
            Self::parse_atom_feed(&feed, source_name, show_author)
        } else {
            anyhow::bail!("Failed to parse feed as RSS or Atom: {}", url)
        }
    }

    fn parse_rss_channel(
        channel: &Channel,
        source_name: &str,
        show_author: bool,
    ) -> Result<Vec<FeedEntry>> {
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

            let display_name = if show_author {
                item.author()
                    .or_else(|| {
                        item.dublin_core_ext()
                            .and_then(|dc| dc.creators().first().map(|s| s.as_str()))
                    })
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
                title_original: None,
            });
        }

        Ok(entries)
    }

    fn parse_atom_feed(
        feed: &atom_syndication::Feed,
        source_name: &str,
        show_author: bool,
    ) -> Result<Vec<FeedEntry>> {
        let mut entries = Vec::new();
        let today = Local::now().date_naive();

        for entry in &feed.entries {
            let title = if entry.title.is_empty() {
                "(No title)".to_string()
            } else {
                entry.title.clone()
            };

            // Prefer rel="alternate" link, fall back to first link
            let link = entry
                .links
                .iter()
                .find(|l| l.rel.as_deref() == Some("alternate"))
                .or_else(|| entry.links.first())
                .map(|l| l.href.clone())
                .unwrap_or_default();

            // Parse date: prefer published, fall back to updated
            let date_str = entry
                .published
                .as_deref()
                .unwrap_or(&entry.updated);

            let parsed_date = DateTime::parse_from_rfc3339(date_str)
                .map(|dt| dt.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now());

            let local_date = Local.from_utc_datetime(&parsed_date.naive_utc());
            let timestamp = parsed_date.timestamp();

            let formatted_date = if local_date.date_naive() == today {
                local_date.format("%H:%M").to_string()
            } else {
                local_date.format("%b %d, %H:%M").to_string()
            };

            let display_name = if show_author {
                entry
                    .authors
                    .first()
                    .map(|a| {
                        // Reddit author names often start with /u/
                        a.name.trim_start_matches("/u/").to_string()
                    })
                    .unwrap_or_else(|| source_name.to_string())
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
                title_original: None,
            });
        }

        Ok(entries)
    }

    fn refresh_current_category(&mut self) {
        let category = self.current_category_name().to_string();
        match self.fetch_feeds(&category) {
            Ok(entries) => {
                self.entries.insert(category, entries);
                self.last_refresh = Instant::now();
            }
            Err(_) => {}
        }
        self.trigger_translation();
    }

    fn load_or_refresh(&mut self) {
        let category = self.current_category_name().to_string();
        if let Some(cached) = self.load_cached_feed(&category) {
            let age = Utc::now().timestamp() - cached.created_at;
            if age < REFRESH_INTERVAL as i64 && !cached.entries.is_empty() {
                self.entries.insert(category, cached.entries);
                self.trigger_translation();
                return;
            }
        }
        self.refresh_current_category();
    }

    fn next_category(&mut self) {
        self.current_category = (self.current_category + 1) % self.categories.len();
        self.selected = None;
        self.reset_marquee();
        self.load_or_refresh();
    }

    fn prev_category(&mut self) {
        if self.current_category == 0 {
            self.current_category = self.categories.len() - 1;
        } else {
            self.current_category -= 1;
        }
        self.selected = None;
        self.reset_marquee();
        self.load_or_refresh();
    }

    fn select_category(&mut self, idx: usize) {
        if idx < self.categories.len() {
            self.current_category = idx;
            self.selected = None;
            self.reset_marquee();
            self.load_or_refresh();
        }
    }

    fn move_down(&mut self) {
        self.reset_marquee();
        let limit = self.row_limit();
        if limit == 0 {
            return;
        }
        self.selected = Some(match self.selected {
            Some(i) => {
                if i + 1 >= limit {
                    0
                } else {
                    i + 1
                }
            }
            None => 0,
        });
    }

    fn move_up(&mut self) {
        self.reset_marquee();
        let limit = self.row_limit();
        if limit == 0 {
            return;
        }
        self.selected = Some(match self.selected {
            Some(i) => {
                if i == 0 {
                    limit - 1
                } else {
                    i - 1
                }
            }
            None => limit - 1,
        });
    }

    fn page_down(&mut self) {
        self.reset_marquee();
        let limit = self.row_limit();
        if limit == 0 {
            return;
        }
        self.selected = Some(match self.selected {
            Some(i) => {
                if i + 10 >= limit {
                    0
                } else {
                    i + 10
                }
            }
            None => 0,
        });
    }

    fn page_up(&mut self) {
        self.reset_marquee();
        let limit = self.row_limit();
        if limit == 0 {
            return;
        }
        self.selected = Some(match self.selected {
            Some(i) => {
                if (i as i32 - 10) < 0 {
                    limit - 1
                } else {
                    i - 10
                }
            }
            None => limit - 1,
        });
    }

    fn go_top(&mut self) {
        self.reset_marquee();
        if self.row_limit() > 0 {
            self.selected = Some(0);
        }
    }

    fn go_bottom(&mut self) {
        self.reset_marquee();
        let limit = self.row_limit();
        if limit > 0 {
            self.selected = Some(limit - 1);
        }
    }

    fn deselect(&mut self) {
        self.reset_marquee();
        self.selected = None;
    }

    fn open_selected(&mut self) {
        if let Some(i) = self.selected {
            let url = self
                .current_entries()
                .get(i)
                .map(|e| e.url.clone());
            if let Some(url) = url {
                if self.gemini_api_key.is_some() {
                    self.summarizing = true;
                    self.summarize_url = url;
                } else {
                    let _ = open::that(&url);
                }
            }
        }
    }

    fn reset_marquee(&mut self) {
        self.marquee_shift = 0;
        self.marquee_direction = MarqueeDirection::Left;
    }

    fn enter_number_mode(&mut self) {
        self.pre_input_selected = self.selected;
        self.input_mode = InputMode::NumberJump;
        self.input_number.clear();
        self.selected = None;
        self.reset_marquee();
    }

    fn exit_number_mode(&mut self, apply: bool) {
        if apply && !self.input_number.is_empty() {
            if let Ok(n) = self.input_number.parse::<usize>() {
                let limit = self.row_limit();
                if n >= 1 && n <= limit {
                    self.selected = Some(n - 1);
                } else {
                    self.selected = self.pre_input_selected;
                }
            } else {
                self.selected = self.pre_input_selected;
            }
        } else {
            self.selected = self.pre_input_selected;
        }
        self.input_mode = InputMode::Normal;
        self.input_number.clear();
        self.pre_input_selected = None;
        self.reset_marquee();
    }

    fn get_loading_state(&self) -> LoadingState {
        self.loading_state.lock().unwrap().clone()
    }

    fn tick_marquee(&mut self) {
        if self.selected.is_none() || self.input_mode == InputMode::NumberJump {
            return;
        }

        let speed = if self.marquee_direction == MarqueeDirection::Left {
            MARQUEE_SPEED
        } else {
            MARQUEE_SPEED_RETURN
        };

        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs_f64();
        let current_tick = (now * speed) as u64;

        if current_tick != self.marquee_tick_count {
            self.marquee_tick_count = current_tick;
            match self.marquee_direction {
                MarqueeDirection::Left => {
                    self.marquee_shift += 1;
                }
                MarqueeDirection::Right => {
                    self.marquee_shift -= 1;
                    if self.marquee_shift <= 0 {
                        self.marquee_shift = 0;
                        self.marquee_direction = MarqueeDirection::Left;
                    }
                }
            }
        }
    }

    fn trigger_translation(&self) {
        let api_key = match &self.gemini_api_key {
            Some(k) => k.clone(),
            None => return,
        };

        // Check if already translating
        {
            let in_progress = self.translating_in_progress.lock().unwrap();
            if *in_progress {
                return;
            }
        }

        let category = self.current_category_name().to_string();
        let titles: Vec<String> = self
            .current_entries()
            .iter()
            .map(|e| {
                e.title_original
                    .as_ref()
                    .unwrap_or(&e.title)
                    .clone()
            })
            .collect();

        if titles.is_empty() {
            return;
        }

        // Check if all titles are already in cache
        {
            let cache = self.translation_cache.lock().unwrap();
            let all_cached = titles.iter().all(|t| cache.contains_key(t));
            if all_cached {
                // Apply from cache directly
                let mut translations = HashMap::new();
                for t in &titles {
                    if let Some(tr) = cache.get(t) {
                        translations.insert(t.clone(), tr.clone());
                    }
                }
                let mut pending = self.pending_translations.lock().unwrap();
                pending.insert(category, translations);
                let mut needs = self.needs_redraw.lock().unwrap();
                *needs = true;
                return;
            }
        }

        let translating = Arc::clone(&self.translating_in_progress);
        let cache_arc = Arc::clone(&self.translation_cache);
        let pending_arc = Arc::clone(&self.pending_translations);
        let needs_arc = Arc::clone(&self.needs_redraw);

        {
            let mut in_progress = translating.lock().unwrap();
            *in_progress = true;
        }

        std::thread::spawn(move || {
            let mut cache = cache_arc.lock().unwrap().clone();
            let translations = translate_titles_batch(&titles, &api_key, &mut cache);

            // Save updated cache
            {
                let mut shared_cache = cache_arc.lock().unwrap();
                *shared_cache = cache.clone();
            }
            save_translation_cache(&cache);

            // Store pending translations
            {
                let mut pending = pending_arc.lock().unwrap();
                pending.insert(category, translations);
            }

            // Signal main loop
            {
                let mut needs = needs_arc.lock().unwrap();
                *needs = true;
            }

            {
                let mut in_progress = translating.lock().unwrap();
                *in_progress = false;
            }
        });
    }

    fn apply_pending_translations(&mut self) {
        let pending: HashMap<String, HashMap<String, String>> = {
            let mut pending = self.pending_translations.lock().unwrap();
            std::mem::take(&mut *pending)
        };

        for (category, translations) in pending {
            if let Some(entries) = self.entries.get_mut(&category) {
                for entry in entries.iter_mut() {
                    let original = entry
                        .title_original
                        .as_ref()
                        .unwrap_or(&entry.title)
                        .clone();
                    if let Some(translated) = translations.get(&original) {
                        if entry.title_original.is_none() {
                            entry.title_original = Some(entry.title.clone());
                        }
                        entry.title = translated.clone();
                    }
                }
            }
        }
    }

    fn do_summarize(&mut self) {
        let url = self.summarize_url.clone();
        let api_key = match &self.gemini_api_key {
            Some(k) => k.clone(),
            None => {
                self.summarizing = false;
                return;
            }
        };

        let summary = summarize_with_gemini(&url, &api_key);

        let width = (self.terminal_width as f32 * 0.8) as usize;
        let content_width = width.saturating_sub(4).max(10);
        self.modal_raw_text = summary.clone();
        self.modal_wrapped_width = self.terminal_width;
        self.modal_text = wrap_text_for_display(&summary, content_width);
        self.modal_scroll = 0;
        self.show_modal = true;
        self.summarizing = false;
    }
}

// ── Unicode-width helpers ──

fn display_width(s: &str) -> usize {
    s.chars()
        .map(|c| UnicodeWidthChar::width(c).unwrap_or(0))
        .sum()
}

fn truncate_to_width(s: &str, max: usize) -> String {
    let mut w = 0;
    let mut result = String::new();
    for c in s.chars() {
        let cw = UnicodeWidthChar::width(c).unwrap_or(0);
        if w + cw > max {
            break;
        }
        result.push(c);
        w += cw;
    }
    // Pad to exact width
    while w < max {
        result.push(' ');
        w += 1;
    }
    result
}

fn slice_text_marquee(
    s: &str,
    max_width: usize,
    shift: i32,
    marquee_direction: &mut MarqueeDirection,
) -> String {
    let string_length = display_width(s) as i32;
    let max_w = max_width as i32;

    if string_length <= max_w {
        return truncate_to_width(s, max_width);
    }

    // Check direction flip conditions
    let effective_shift;
    if string_length - shift + MARQUEE_DELAY_RETURN < max_w || shift == -1 {
        *marquee_direction = if *marquee_direction == MarqueeDirection::Left {
            MarqueeDirection::Right
        } else {
            MarqueeDirection::Left
        };
    }

    if *marquee_direction == MarqueeDirection::Left {
        if shift < MARQUEE_DELAY {
            effective_shift = 0;
        } else {
            effective_shift = shift - MARQUEE_DELAY;
        }
    } else {
        effective_shift = shift;
    }

    // Clamp shift so we don't scroll too far
    let clamped_shift = if string_length - effective_shift + max_w / 4 < max_w {
        string_length - max_w + max_w / 4
    } else {
        effective_shift
    };

    // Build result by skipping `clamped_shift` display-width units
    let mut result = String::new();
    let mut w = 0; // accumulated display width
    let mut out_w = 0;

    for c in s.chars() {
        let cw = UnicodeWidthChar::width(c).unwrap_or(0) as i32;
        w += cw;

        if w <= clamped_shift {
            // Before visible window - but handle double-width boundary
            if w == clamped_shift && cw == 2 {
                // We're exactly at a double-width char boundary, skip
            }
            continue;
        }

        // If we skipped into the middle of a double-width char
        if w - cw < clamped_shift && cw == 2 {
            result.push(' ');
            out_w += 1;
        }

        // Check if this char fits before adding
        if out_w + cw > max_w {
            break;
        }

        result.push(c);
        out_w += cw;
    }

    // Pad if needed
    while out_w < max_w {
        result.push(' ');
        out_w += 1;
    }

    result
}

// ── Rendering ──

fn render_category_bar(f: &mut Frame, app: &App) {
    let frame_width = f.size().width;
    let width = frame_width as usize;

    // Fill entire row with dots in categorybg color
    let dots: String = ".".repeat(width);
    let dot_style = Style::default()
        .fg(app.colors.categorybg)
        .bg(app.colors.categorybg);

    let buf = f.buffer_mut();
    buf.set_string(0, 0, &dots, dot_style);

    // Draw each category label
    let mut x: u16 = 1;
    for (idx, cat_key) in app.categories.iter().enumerate() {
        let title = app.category_titles.get(cat_key).unwrap_or(cat_key);
        let label = format!(" {} ", title);
        let label_len = label.len() as u16;

        let style = if idx == app.current_category {
            Style::default()
                .fg(app.colors.categoryfg_s)
                .bg(app.colors.categorybg_s)
        } else {
            Style::default()
                .fg(app.colors.categoryfg)
                .bg(app.colors.categorybg)
        };

        if x + label_len <= frame_width {
            buf.set_string(x, 0, &label, style);
        }
        x += label_len + 2;
    }
}

fn render_alert(f: &mut Frame, app: &App, text: &str) {
    let space = 3;
    let display_text = format!("{}{}{}", " ".repeat(space), text, " ".repeat(space));
    let text_len = display_text.len() as u16;
    let x = f.size().width.saturating_sub(text_len);

    let style = Style::default()
        .fg(app.colors.alertfg)
        .bg(app.colors.alertbg);

    f.buffer_mut().set_string(x, 0, &display_text, style);
}

fn render_entries(f: &mut Frame, app: &mut App) {
    let width = f.size().width;
    let height = f.size().height;

    // Clone entries data we need to avoid borrow conflicts
    let entry_data: Vec<(String, String, String)> = app
        .current_entries()
        .iter()
        .map(|e| (e.source_name.clone(), e.title.clone(), e.pub_date.clone()))
        .collect();

    let row_limit = app.row_limit();
    let is_number_mode = app.input_mode == InputMode::NumberJump;
    let selected = app.selected;
    let colors = app.colors.clone();
    let input_number = app.input_number.clone();
    let marquee_shift = app.marquee_shift;

    let buf = f.buffer_mut();

    for i in 0..row_limit {
        let row = (i + 1) as u16;
        if row >= height {
            break;
        }

        let is_selected = selected == Some(i) && !is_number_mode;

        // Fill background
        let bg = if is_selected {
            colors.selected_bg
        } else {
            Color::Black
        };
        let fill_style = Style::default().fg(bg).bg(bg);
        let spaces = " ".repeat(width as usize);
        buf.set_string(0, row, &spaces, fill_style);

        if i >= entry_data.len() {
            continue;
        }
        let (ref source_name, ref title, ref pub_date) = entry_data[i];

        // Number column in number mode
        if is_number_mode {
            let num_str = format!("{:>3}", i + 1);
            let num_fg = if !input_number.is_empty() {
                if let Ok(n) = input_number.parse::<usize>() {
                    if n == i + 1 {
                        colors.numberselected
                    } else {
                        colors.number
                    }
                } else {
                    colors.number
                }
            } else {
                colors.number
            };
            let num_style = Style::default().fg(num_fg).bg(Color::Black);
            buf.set_string(1, row, &num_str, num_style);
        }

        let col_offset: u16 = if is_number_mode { 4 } else { 0 };

        // Source name field (col=1 in Python, space-filled to 20 chars)
        let source_col = SOURCE_COL + col_offset;
        let source_text = format!(" {} ", source_name);
        let source_display = truncate_to_width(&source_text, 19);

        let (source_fg, source_bg) = if is_selected {
            (Color::Black, colors.selected_bg)
        } else {
            (colors.source, Color::Black)
        };
        let source_style = Style::default().fg(source_fg).bg(source_bg);
        set_string_unicode(buf, source_col, row, &source_display, source_style);

        // Title field (col=20 in Python)
        let title_col = TITLE_COL + col_offset;
        let pub_date_len = display_width(pub_date) as u16 + 2;
        let title_max_width =
            (width.saturating_sub(title_col + pub_date_len)) as usize;

        let title_text = if is_selected {
            slice_text_marquee(
                title,
                title_max_width,
                marquee_shift,
                &mut app.marquee_direction,
            )
        } else {
            truncate_to_width(title, title_max_width)
        };

        let title_prefix = " ";
        let (title_fg, title_bg) = if is_selected {
            (Color::Black, colors.selected_bg)
        } else {
            (colors.default, Color::Black)
        };
        let title_style = Style::default().fg(title_fg).bg(title_bg);
        let title_x = title_col.saturating_sub(1);
        set_string_unicode(buf, title_x, row, title_prefix, title_style);
        set_string_unicode(buf, title_col, row, &title_text, title_style);

        // PubDate field (right-aligned, col=-1 in Python)
        let date_text = format!(" {} ", pub_date);
        let date_display_w = display_width(&date_text) as u16;
        let date_x = width.saturating_sub(date_display_w);

        let (date_fg, date_bg) = if is_selected {
            (Color::Black, colors.selected_bg)
        } else {
            (colors.time, Color::Black)
        };
        let date_style = Style::default().fg(date_fg).bg(date_bg);
        set_string_unicode(buf, date_x, row, &date_text, date_style);
    }

    // Clear remaining rows below entries
    for row in (row_limit + 1) as u16..height {
        let clear_style = Style::default().fg(Color::Black).bg(Color::Black);
        let spaces = " ".repeat(width as usize);
        buf.set_string(0, row, &spaces, clear_style);
    }
}

fn render_help(f: &mut Frame, app: &App) {
    let help_lines = vec![
        "",
        "            [Up], [Down], [W], [S], [J], [K] : Select from list",
        "[Shift]+[Up], [Shift]+[Down], [PgUp], [PgDn] : Quickly select from list",
        "                                         [O] : Open canonical link",
        "                                         [:] : Select by typing a number from list",
        "                        [Tab], [Shift]+[Tab] : Change the category tab",
        "                             [Q], [Ctrl]+[C] : Quit",
        "",
    ];

    let lines_count = help_lines.len();
    let max_width = help_lines.iter().map(|l| l.len()).max().unwrap_or(0) + 2;

    let width = f.size().width;
    let height = f.size().height;

    let buf = f.buffer_mut();

    // Clear screen
    let clear_style = Style::default().fg(Color::Black).bg(Color::Black);
    for y in 0..height {
        let spaces = " ".repeat(width as usize);
        buf.set_string(0, y, &spaces, clear_style);
    }

    let top = (height as usize / 2).saturating_sub(lines_count / 2);
    let left = (width as usize / 2).saturating_sub(max_width / 2);

    let style = Style::default()
        .fg(app.colors.alertfg)
        .bg(app.colors.alertbg);

    for (i, line) in help_lines.iter().enumerate() {
        let y = (top + i) as u16;
        if y >= height {
            break;
        }
        // Fill background for the line width
        let bg_fill = " ".repeat(max_width);
        let x = left.saturating_sub(1) as u16;
        buf.set_string(x, y, &bg_fill, style);
        buf.set_string(left as u16, y, line, style);
    }
}

fn render_modal(f: &mut Frame, app: &App) {
    let width = f.size().width;
    let height = f.size().height;

    let modal_width = (width as f32 * 0.8) as usize;
    let modal_height = (height as f32 * 0.8) as usize;
    let start_x = ((width as usize).saturating_sub(modal_width)) / 2;
    let start_y = ((height as usize).saturating_sub(modal_height)) / 2;

    let buf = f.buffer_mut();

    let bg_style = Style::default()
        .fg(app.colors.categoryfg)
        .bg(app.colors.categorybg);
    let border_style = Style::default()
        .fg(app.colors.categoryfg_s)
        .bg(app.colors.categorybg);

    // Clear modal area
    for y in 0..modal_height {
        let py = (start_y + y) as u16;
        if py >= height {
            break;
        }
        let spaces = " ".repeat(modal_width);
        buf.set_string(start_x as u16, py, &spaces, bg_style);
    }

    // Draw borders
    let top_border = "-".repeat(modal_width);
    let bottom_border = "-".repeat(modal_width);
    buf.set_string(start_x as u16, start_y as u16, &top_border, border_style);
    if start_y + modal_height - 1 < height as usize {
        buf.set_string(
            start_x as u16,
            (start_y + modal_height - 1) as u16,
            &bottom_border,
            border_style,
        );
    }

    // Side borders
    for y in start_y..(start_y + modal_height) {
        let py = y as u16;
        if py >= height {
            break;
        }
        buf.set_string(start_x as u16, py, "|", border_style);
        if start_x + modal_width - 1 < width as usize {
            buf.set_string((start_x + modal_width - 1) as u16, py, "|", border_style);
        }
    }

    // Display text content
    let content_height = modal_height.saturating_sub(3); // top border + bottom border + esc label
    let content_x = (start_x + 2) as u16;
    let content_width = modal_width.saturating_sub(4);

    for (i, line) in app.modal_text.iter().skip(app.modal_scroll).enumerate() {
        if i >= content_height {
            break;
        }
        let py = (start_y + 1 + i) as u16;
        if py >= height {
            break;
        }
        let display_line = truncate_to_width(line, content_width);
        set_string_unicode(buf, content_x, py, &display_line, bg_style);
    }

    // ESC Close label
    let esc_label = "[ESC] Close";
    let esc_style = Style::default()
        .fg(app.colors.categoryfg_s)
        .bg(app.colors.categorybg_s);
    let esc_x = start_x + (modal_width.saturating_sub(esc_label.len())) / 2;
    if start_y + modal_height >= 2 {
        let esc_y = (start_y + modal_height - 2) as u16;
        if esc_y < height {
            buf.set_string(esc_x as u16, esc_y, esc_label, esc_style);
        }
    }
}

/// Set a unicode-aware string into the buffer, handling double-width chars properly
fn set_string_unicode(buf: &mut Buffer, x: u16, y: u16, s: &str, style: Style) {
    let buf_width = buf.area().width;
    let buf_height = buf.area().height;
    if y >= buf_height || x >= buf_width {
        return;
    }
    let mut cx = x;
    for c in s.chars() {
        if cx >= buf_width {
            break;
        }
        let cw = UnicodeWidthChar::width(c).unwrap_or(0);
        if cw == 0 {
            continue;
        }
        if cx + (cw as u16) > buf_width {
            break;
        }
        buf.get_mut(cx, y).set_char(c).set_style(style);
        // For double-width chars, the next cell should be empty
        if cw == 2 && cx + 1 < buf_width {
            buf.get_mut(cx + 1, y).set_char(' ').set_style(style);
        }
        cx += cw as u16;
    }
}

fn ui(f: &mut Frame, app: &mut App) {
    app.terminal_width = f.size().width;
    app.terminal_height = f.size().height;

    if app.show_help {
        render_help(f, app);
        return;
    }

    render_category_bar(f, app);
    render_entries(f, app);

    // Loading indicator
    let loading_state = app.get_loading_state();
    if loading_state.is_loading {
        render_alert(f, app, "LOADING");
    }

    // Translating indicator
    {
        let translating = app.translating_in_progress.lock().unwrap();
        if *translating && !loading_state.is_loading {
            render_alert(f, app, "TRANSLATING...");
        }
    }

    // Summarizing indicator
    if app.summarizing {
        render_alert(f, app, "SUMMARIZING WITH GEMINI...");
    }

    // Modal overlay
    if app.show_modal {
        // Re-wrap modal text if terminal width changed
        if app.modal_wrapped_width != app.terminal_width && !app.modal_raw_text.is_empty() {
            let width = (app.terminal_width as f32 * 0.8) as usize;
            let content_width = width.saturating_sub(4).max(10);
            app.modal_text = wrap_text_for_display(&app.modal_raw_text, content_width);
            app.modal_wrapped_width = app.terminal_width;
            let max_scroll = app.modal_text.len().saturating_sub(
                ((app.terminal_height as f32 * 0.8) as usize).saturating_sub(3),
            );
            app.modal_scroll = app.modal_scroll.min(max_scroll);
        }
        render_modal(f, app);
    }
}

fn main() -> Result<()> {
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let mut app = App::new()?;
    app.load_or_refresh();

    let tick_rate = Duration::from_millis(20);

    loop {
        // Check if summarizing needs to be done (2-step state machine)
        if app.summarizing && !app.show_modal {
            // Render once to show "SUMMARIZING..." alert
            terminal.draw(|f| ui(f, &mut app))?;
            // Now do the blocking API call
            app.do_summarize();
            continue;
        }

        terminal.draw(|f| ui(f, &mut app))?;

        let timeout = tick_rate
            .checked_sub(Instant::now().elapsed())
            .unwrap_or(Duration::from_millis(0));

        if crossterm::event::poll(timeout)? {
            if let Event::Key(key) = event::read()? {
                // Modal key handling
                if app.show_modal {
                    match key.code {
                        KeyCode::Esc => {
                            app.show_modal = false;
                            app.modal_text.clear();
                            app.modal_raw_text.clear();
                            app.modal_wrapped_width = 0;
                            app.modal_scroll = 0;
                        }
                        KeyCode::Down | KeyCode::Char('j') | KeyCode::Char('J') => {
                            let max_scroll = app
                                .modal_text
                                .len()
                                .saturating_sub((app.terminal_height as f32 * 0.8) as usize - 3);
                            if app.modal_scroll < max_scroll {
                                app.modal_scroll += 1;
                            }
                        }
                        KeyCode::Up | KeyCode::Char('k') | KeyCode::Char('K') => {
                            if app.modal_scroll > 0 {
                                app.modal_scroll -= 1;
                            }
                        }
                        KeyCode::PageDown => {
                            let page = ((app.terminal_height as f32 * 0.8) as usize).saturating_sub(3);
                            let max_scroll = app
                                .modal_text
                                .len()
                                .saturating_sub((app.terminal_height as f32 * 0.8) as usize - 3);
                            app.modal_scroll = (app.modal_scroll + page).min(max_scroll);
                        }
                        KeyCode::PageUp => {
                            let page = ((app.terminal_height as f32 * 0.8) as usize).saturating_sub(3);
                            app.modal_scroll = app.modal_scroll.saturating_sub(page);
                        }
                        _ => {}
                    }
                    continue;
                }

                if app.show_help {
                    app.show_help = false;
                    continue;
                }

                if app.input_mode == InputMode::NumberJump {
                    match key.code {
                        KeyCode::Enter | KeyCode::Char(':') => {
                            let apply = key.code == KeyCode::Enter;
                            app.exit_number_mode(apply);
                        }
                        KeyCode::Char(c) if c.is_ascii_digit() => {
                            if app.input_number.len() < 3 {
                                app.input_number.push(c);
                            }
                        }
                        KeyCode::Backspace => {
                            if app.input_number.is_empty() {
                                app.exit_number_mode(false);
                            } else {
                                app.input_number.pop();
                            }
                        }
                        KeyCode::Esc => {
                            app.exit_number_mode(false);
                        }
                        _ => {}
                    }
                    continue;
                }

                match key.code {
                    KeyCode::Char('q') | KeyCode::Char('Q') => break,
                    KeyCode::Char('c')
                        if key.modifiers.contains(KeyModifiers::CONTROL) =>
                    {
                        break
                    }
                    KeyCode::Esc => app.deselect(),
                    KeyCode::Tab => app.next_category(),
                    KeyCode::BackTab => app.prev_category(),
                    KeyCode::Down | KeyCode::Char('j') | KeyCode::Char('J') => {
                        if key.modifiers.contains(KeyModifiers::SHIFT) {
                            app.page_down();
                        } else {
                            app.move_down();
                        }
                    }
                    KeyCode::Char('s') | KeyCode::Char('S') => app.move_down(),
                    KeyCode::Up | KeyCode::Char('k') | KeyCode::Char('K') => {
                        if key.modifiers.contains(KeyModifiers::SHIFT) {
                            app.page_up();
                        } else {
                            app.move_up();
                        }
                    }
                    KeyCode::Char('w') | KeyCode::Char('W') => app.move_up(),
                    KeyCode::PageDown => app.page_down(),
                    KeyCode::PageUp => app.page_up(),
                    KeyCode::Enter
                    | KeyCode::Char('o')
                    | KeyCode::Char('O')
                    | KeyCode::Char(' ') => app.open_selected(),
                    KeyCode::Char('r') | KeyCode::Char('R') => {
                        app.selected = None;
                        app.reset_marquee();
                        app.refresh_current_category();
                    }
                    KeyCode::Char(':') => app.enter_number_mode(),
                    KeyCode::Char('h') | KeyCode::Char('H') | KeyCode::Char('?') => {
                        app.show_help = true;
                    }
                    KeyCode::Char('g') => app.go_top(),
                    KeyCode::Char('G') => app.go_bottom(),
                    KeyCode::Char('1') => app.select_category(0),
                    KeyCode::Char('2') => app.select_category(1),
                    KeyCode::Char('3') => app.select_category(2),
                    KeyCode::Char('4') => app.select_category(3),
                    _ => {}
                }
            }
        }

        // Marquee tick
        app.tick_marquee();

        // Check for pending translations
        {
            let mut needs = app.needs_redraw.lock().unwrap();
            if *needs {
                *needs = false;
                drop(needs);
                app.apply_pending_translations();
            }
        }

        // Auto-refresh check
        if app.last_refresh.elapsed() >= Duration::from_secs(REFRESH_INTERVAL) {
            let loading_state = app.get_loading_state();
            if !loading_state.is_loading {
                app.refresh_current_category();
            }
        }
    }

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;

    Ok(())
}
