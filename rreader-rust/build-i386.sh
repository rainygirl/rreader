#!/bin/bash

set -e

echo "=== rreader Rust build for i386 ==="

if ! command -v rustup &> /dev/null; then
    echo "Rust not found. Installing..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi

echo "Adding i686 target..."
rustup target add i686-unknown-linux-gnu

if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y gcc-multilib g++-multilib
    elif command -v yum &> /dev/null; then
        sudo yum install -y glibc-devel.i686 libgcc.i686
    fi
fi

echo "Building for i686-unknown-linux-gnu..."
cargo build --release --target i686-unknown-linux-gnu

echo ""
echo "Build complete!"
echo "Binary location: target/i686-unknown-linux-gnu/release/rreader"
echo ""
echo "To run: ./target/i686-unknown-linux-gnu/release/rreader"
