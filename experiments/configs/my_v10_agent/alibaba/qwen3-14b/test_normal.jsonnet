local experiment_prompts_path = std.extVar("APPWORLD_EXPERIMENT_PROMPTS_PATH");
local experiment_configs_path = std.extVar("APPWORLD_EXPERIMENT_CONFIGS_PATH");
local experiment_code_path = std.extVar("APPWORLD_EXPERIMENT_CODE_PATH");
{
    "type": "my",
    "config": {
        "agent": {
            "type": "peter",
            "model_config": {
                "client_name": "litellm",
                "api_type": "chat_completions",
                "name": "openrouter/qwen/qwen3.5-27B",
                "stop": "['<|endoftext|>', '<|eot_id|>', '<|start_header_id|>']",
                "temperature": 0.1,
                "seed": 100,
                "drop_reasoning_content": false,
                "cost_per_token": {"input_cache_hit": 8.8e-07, "input_cache_miss": 8.8e-07, "input_cache_write": 0.0, "output": 8.8e-07},
                "retry_after_n_seconds": 15,
                "use_cache": false,
                "max_retries": 100,
                "max_tokens": 256,
                "max_completion_tokens": 512,
                "provider": {
                    "require_parameters": true,
                    "allow_fallbacks": false,
                    "quantizations": [
                        "bf16"
                    ],
                    "order": [
                        "alibaba",
                        "phala", 
                        "novita/bf16",
                    ],
                },
            },
            "appworld_config": {
                "random_seed": 1,
                "raise_on_extra_parameters": true,
                "raise_on_unsafe_syntax": false,
            },
            "logger_config": {
                "color": true,
                "verbose": true,
            },
            "usage_tracker_config": {
                "max_cost_overall": 1000,
                "max_cost_per_task": 10,
                "max_output_tokens_per_task": 100000,
            },
            "max_steps": 50,
            "log_lm_calls": true,
            "skip_if_finished": false,
        },
        "dataset": "test_normal",
    },
    "metadata": {
        "model": {
            "file_name": "Qwen/Qwen3-14B",
            "humanized_name": "Qwen3 14B",
            "precise_name": "hosted_vllm/Qwen/Qwen3-14B",
            "creator": "alibaba",
            "provider": "vllm",
        },
        "agent": {
            "file_name": "my_v10_agent",
            "humanized_name": "My V10 Agent",
        },
    },
}
