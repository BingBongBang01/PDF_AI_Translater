# API Reference

This document outlines how to extend the Application Engine using the plugin framework.

## Export Plugin Interface
To add a new Export Format (e.g., `.mobi`):
1. Create a class inheriting from `ExportPlugin` in `services/export/export_manager.py`.
2. Define `format_name` and `supported_extensions`.
3. Implement `export(self, task, profile) -> bool`.
4. Register the plugin in `services/export_service.py` via `self.manager.register_plugin(MyMobiPlugin())`.

## Provider Interface
To add a new Translation LLM API:
1. Create a class inheriting from `BaseProvider` in `services/providers/base/provider.py`.
2. Implement `stream_translate(self, request) -> Generator[str, None, None]`.
3. Register the provider in `services/translation_service.py` via `self.provider_manager.register_provider(MyProvider())`.
