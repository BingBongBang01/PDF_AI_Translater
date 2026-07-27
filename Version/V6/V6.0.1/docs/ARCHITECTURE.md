# Architecture Overview

The V6 application is built upon a strict Layered Service architecture heavily utilizing SOLID principles and Decoupled GUI patterns.

## Core Pillars
1. **EventBus**: All inter-module communication is asynchronous and entirely decoupled. The UI listens to string signals (e.g., `TranslationFinished`, `OCRProgress`) while the backend emits them. This prevents GUI thread locking.
2. **ServiceLocator**: The Application state exposes a global `ServiceLocator` singleton. The GUI requests services like `TranslationService` or `ExportService` from the locator rather than instantiating them directly.
3. **Background Queues**: Long-running jobs are sent to `QRunnable` wrappers (`ExportWorker`, `OCRWorker`) and queued into a global `QThreadPool` via `WorkerManager`.

## Modules
- **`core/`**: Non-business logic helpers. Holds Session, Configurations, ThreadPool, EventBus, and the Service Locator.
- **`engine/`**: The hardcore math and file I/O operations (PyMuPDF rendering, Tesseract bindings). Completely unaware of the UI.
- **`services/`**: The orchestration facades. `TranslationService` orchestrates Chunker -> Prompts -> Providers -> Memory Cache.
- **`tests/`**: Unit tests utilizing PyTest.
- **`scripts/`**: CI/CD QA auditing and profiling scripts.
