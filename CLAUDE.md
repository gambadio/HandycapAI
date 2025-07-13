# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HandycapAI is a macOS voice-first assistant designed for hands-free productivity and accessibility. It uses local/cloud speech recognition (Whisper), integrates with OpenAI's GPT-4o (both chat completions and realtime API), and provides custom Python function execution capabilities.

## Development Commands

### Running the Application
```bash
# Activate virtual environment
source .venv/bin/activate

# Run from source
python main.py
```

### Building and Packaging
```bash
# Build standalone .app bundle
python packaging/setup.py py2app

# Notarize for distribution (requires Apple Developer account)
export AC_PASSWORD="@keychain:MyNotarizePwd"
./packaging/notarize.sh

# After notarization email arrives (~2 min)
xcrun stapler staple dist/HandycapAI.app

# Optional: Create .dmg
hdiutil create -volname HandycapAI -srcfolder dist/HandycapAI.app -ov -format UDZO HandycapAI.dmg
```

### Testing
```bash
# Run tests with pytest
pytest

# Note: Test coverage is minimal - only a basic test file exists currently
```

### Code Quality
The README mentions pre-commit with ruff & black, but no configuration file exists yet. When implementing:
```bash
# Install pre-commit hooks (when config is added)
pre-commit install
```

## Architecture

### Core Components

1. **LLM Integration** (`llm/`)
   - `chat.py`: OpenAI chat completions streaming
   - `realtime_*.py`: Two implementations of OpenAI Realtime API (basic text-only, advanced with audio)
   - `tools.py`: Custom function handling with `SecureFunctionExecutor` for sandboxed execution

2. **Voice Processing** (`voice/`)
   - `stt.py`: Speech-to-text using local faster-whisper or cloud Whisper API
   - `tts.py`: Text-to-speech via OpenAI API
   - `wake.py`: Wake word detection using Picovoice Porcupine
   - `realtime_audio.py`: Real-time audio I/O handling

3. **UI Layer** (`ui/`)
   - Built with PySide6 (Qt for Python) + qasync for asyncio integration
   - `chat_interface.py`: Main chat window
   - `tray.py`: Menu bar icon and controls
   - All UI components inherit from Qt widgets with async support

4. **Persistence**
   - SQLite with WAL mode for chat history
   - Encrypted API key storage using Fernet encryption
   - Settings in `~/Library/Preferences/com.handycapai.app.plist`

### Key Design Patterns

1. **Async Everything**: The entire application runs on Qt's event loop integrated with asyncio via qasync
2. **Security**: Custom functions run in a sandboxed environment with AST validation
3. **Fallback Strategy**: Local Whisper falls back to cloud API on GPU memory issues
4. **Platform Integration**: Uses pyobjc for macOS-specific features (screenshots, text insertion)

## Platform Requirements

- macOS 10.15+ (Intel & Apple Silicon)
- Python 3.11 or 3.12
- PortAudio (via Homebrew if needed)
- API Keys: OpenAI (required), Picovoice (for wake word)

## Common Development Tasks

### Adding a New Custom Function
Custom functions are defined in the Settings UI and stored in the database. They must follow the sandbox security model implemented in `llm/tools.py`.

### Modifying Voice Processing
- STT changes: `voice/stt.py` handles both local and cloud implementations
- Wake word: Uses `.ppn` files in `wake_words/` directory
- Audio pipeline: 24kHz capture with WebRTC VAD

### UI Modifications
- Follow existing PySide6 patterns with qasync integration
- State management through Qt signals/slots
- Icons in `icons/` (grey/cyan/pulse states)

## Security Considerations

- API keys are encrypted with per-machine keys
- Custom functions run in sandboxed environment
- No server-side components - everything runs locally
- Audio only leaves machine when `stt_source = cloud`