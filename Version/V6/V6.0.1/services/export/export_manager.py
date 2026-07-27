from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class ExportProfile:
    """Configuration profile for an export job."""
    format: str
    destination_folder: str
    filename_template: str = "{name}_translated.{ext}"
    overwrite: bool = False
    compress: bool = True
    embed_fonts: bool = True
    embed_images: bool = True
    include_metadata: bool = True
    extra_options: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ExportTask:
    """A single file to be exported within a job."""
    document_id: str
    source_path: str
    target_filename: str
    status: str = "Pending"
    progress: float = 0.0

@dataclass
class ExportJob:
    """A batch job containing multiple ExportTasks."""
    job_id: str
    profile: ExportProfile
    tasks: List[ExportTask] = field(default_factory=list)
    status: str = "Pending"

class ExportPlugin:
    """Base class for format-specific export plugins (PDF, DOCX, HTML, etc.)."""
    def __init__(self):
        self.format_name = "UNKNOWN"
        self.supported_extensions = []

    def export(self, task: ExportTask, profile: ExportProfile) -> bool:
        """Executes the export for a specific task."""
        raise NotImplementedError("Plugins must implement export().")
        
    def validate(self, task: ExportTask) -> list:
        """Returns a list of warnings or errors before export."""
        return []

class ExportManager:
    """Central registry for Export Plugins and Job orchestration."""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ExportManager, cls).__new__(cls)
            cls._instance.plugins = {}
        return cls._instance
        
    def register_plugin(self, plugin: ExportPlugin):
        self.plugins[plugin.format_name] = plugin
        
    def get_plugin(self, format_name: str) -> Optional[ExportPlugin]:
        return self.plugins.get(format_name)
        
    def create_job(self, profile: ExportProfile, tasks: List[ExportTask]) -> ExportJob:
        import uuid
        return ExportJob(job_id=str(uuid.uuid4()), profile=profile, tasks=tasks)
