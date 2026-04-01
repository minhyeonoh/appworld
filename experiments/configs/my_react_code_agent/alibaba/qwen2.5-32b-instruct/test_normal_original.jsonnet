local experiment_prompts_path = std.extVar("APPWORLD_EXPERIMENT_PROMPTS_PATH");
local experiment_configs_path = std.extVar("APPWORLD_EXPERIMENT_CONFIGS_PATH");
local experiment_code_path = std.extVar("APPWORLD_EXPERIMENT_CODE_PATH");
{
    "type": "simplified",
    "config": {
        "agent": {
            "type": "simplified_react_code_agent",
            "model_config": {
                "client_name": "litellm",
                "api_type": "chat_completions",
                "name": "hosted_vllm/Qwen/Qwen2.5-32B-Instruct",
                "stop": "['<|endoftext|>', '<|eot_id|>', '<|start_header_id|>']",
                "temperature": 0.0,
                "seed": 100,
                "drop_reasoning_content": false,
                "cost_per_token": {"input_cache_hit": 8.8e-07, "input_cache_miss": 8.8e-07, "input_cache_write": 0.0, "output": 8.8e-07},
                "retry_after_n_seconds": 15,
                "use_cache": false,
                "max_retries": 100,
                "max_tokens": 1500,
            },
            "appworld_config": {
                "random_seed": 100,
                "raise_on_extra_parameters": true,
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
            "prompt_file_path": experiment_prompts_path + "/react_code_agent/instructions.txt",
            "ignore_multiple_calls": true,
            "max_prompt_length": null,
            "max_output_length": null,
            "max_steps": 50,
            "log_lm_calls": true,
            "skip_if_finished": true,
        },
        "dataset": "test_normal",
    },
    "metadata": {
        "model": {
            "file_name": "Qwen/Qwen2.5-32B-Instruct",
            "humanized_name": "Qwen 2.5 32B Instruct Ollama",
            "precise_name": "hosted_vllm/Qwen/Qwen2.5-32B-Instruct",
            "creator": "qwen",
            "provider": "vllm",
        },
        "agent": {
            "file_name": "simplified_react_code_agent",
            "humanized_name": "ReAct Code Agent",
        },
    },
}