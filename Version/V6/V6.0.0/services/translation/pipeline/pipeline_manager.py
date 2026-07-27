from typing import List, Dict, Any, Optional

class PipelineStage:
    """Base class for any stage in the translation pipeline."""
    def process(self, data: Any) -> Any:
        raise NotImplementedError

class TranslationPipeline:
    """Orchestrates the Document -> Page -> Block -> Chunk -> Provider flow."""
    def __init__(self):
        self.stages: List[PipelineStage] = []
        
    def add_stage(self, stage: PipelineStage) -> None:
        self.stages.append(stage)
        
    def execute(self, document: Any) -> Any:
        current_data = document
        for stage in self.stages:
            current_data = stage.process(current_data)
        return current_data
