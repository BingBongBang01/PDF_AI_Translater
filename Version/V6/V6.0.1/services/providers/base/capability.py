from dataclasses import dataclass

@dataclass(frozen=True)
class ModelCapability:
    context_window: int
    streaming: bool = True
    vision: bool = False
    ocr_capable: bool = False
    thinking_mode: bool = False
    tool_calling: bool = False
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0
