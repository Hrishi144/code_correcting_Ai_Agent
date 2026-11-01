# Models considered for the local coding agent

Recorded: 31 October 2026, Asia/Calcutta.

This document records our discussion and the models screened during internet research. It is a selection record, not a local benchmark or a security certification.

## Selected model and why we picked it

**User-selected model: Qwen2.5-Coder 3B Instruct, Q4_K_M quantization**, recorded on 31 October 2026. This decision supersedes the earlier provisional recommendations of MiniCPM5-2B, Qwen3.5 4B, and Qwen2.5-Coder 7B.

The [Ollama `qwen2.5-coder:3b` package](https://ollama.com/library/qwen2.5-coder:3b) was verified as Q4_K_M, approximately 1.9 GB. Confirm the quantization when downloading because tags can change.

Reasons for this choice:

- **Memory headroom is the user's priority.** On Windows with 16 GB RAM and an RTX 3050 Laptop GPU with 6 GB VRAM, its smaller weights leave more room for context, runtime buffers, and other applications than Qwen2.5-Coder 7B (approximately 4.7 GB) or Qwen3.5 4B Q4_K_M (approximately 3.3 GB). These are package sizes, not measured running memory or guarantees of full GPU residency.
- **Its coding focus matches the first version.** The instruction-tuned model is intended for code generation, reasoning, and repair, making it a relevant baseline for Python and JSON diagnosis, explanations, and proposed fixes.
- **Ollama integration is straightforward.** The existing library package avoids custom model-conversion or chat-template setup for the initial prototype. Inference runs locally without a paid model API.
- **The agent will provide independent checks.** Python compilation checks, JSON parsing and optional schema validation, and relevant behavioural tests will check proposed changes. The user will review the diff before saving, and the application will preserve backups. These safeguards are planned application features, not guarantees provided by the model.

**Tradeoff:** We are choosing a compact coding baseline, not claiming the highest repair accuracy. Complex or multi-file debugging may exceed its capabilities; syntax checks and passing tests cannot establish correctness beyond what they check. MiniCPM5-2B remains a smaller alternative, but the user chose Qwen's coding focus and straightforward Ollama setup. Keep the model configurable so later evaluations can justify a change.

**Initial evaluation settings:** one loaded model, one request at a time, and `num_ctx=4096`. Check `ollama ps` after a representative request for GPU placement and measure latency and memory before increasing context. Use a 20-case Python/JSON evaluation covering generation, syntax errors, runtime errors, logical bugs, malformed JSON, and already-correct files. Record correct repairs, unnecessary changes, explanation accuracy, validation results, and total time including retries.

Selection does not mean installation or evaluation has been completed. The user handles downloads and installations. The 3B model's Qwen Research license is recorded below; it should not be confused with the 7B model's license.

## Project requirements

- Generate code, explain errors, and propose corrections.
- Begin with Python and JSON files, then consider additional domains.
- Run locally through Ollama on Windows.
- Hardware observed: NVIDIA GeForce RTX 3050 Laptop GPU with 6 GB VRAM. System RAM reported by the user: 16 GB.
- Prefer models that can be downloaded and used locally without API usage fees.
- Explain each proposed tool, download, and implementation step before proceeding. The user handles downloads and installations.

Download sizes below are approximate Ollama package sizes for the listed variants. They are not total running memory. Context length, output length, quantization, runtime overhead, and other applications affect memory use. Hardware assessments are estimates, not measurements.

## The nine models discussed directly

| Model and Ollama identifier | Approximate download | Why it entered the discussion | Assessment and selection history |
| --- | --- | --- | --- |
| **Qwen2.5-Coder 3B** - `qwen2.5-coder:3b` | 1.9 GB, Q4_K_M | Coding-focused training covering generation, reasoning, and repair; compact initial prototype. | **Selected by the user for the first version**, prioritizing memory headroom and straightforward Ollama integration. An earlier partial download was stopped and all 18 associated cache and metadata files were removed at the user's request. This selection does not imply a new download has occurred. [Ollama listing](https://ollama.com/library/qwen2.5-coder:3b) |
| **Qwen2.5-Coder 7B** - `qwen2.5-coder:7b` | 4.7 GB | Larger coding-focused candidate to compare for correction quality. | Less GPU memory headroom than 3B; context and runtime overhead matter. No local test established whether it fits fully on the GPU. [Ollama listing](https://ollama.com/library/qwen2.5-coder:7b) |
| **DeepSeek-Coder 6.7B** - `deepseek-coder:6.7b` | 3.8 GB | Another coding specialist, trained heavily on programming data. | Earlier alternative to Qwen. Not downloaded or evaluated by us. It was not included in the newer comparison table below, so that table cannot establish its relative ranking. [Ollama listing](https://ollama.com/library/deepseek-coder:6.7b) |
| **Phi-4 Mini 3.8B** - `phi4-mini:3.8b` | 2.5 GB | Compact instruction-following and reasoning model; potentially useful for explanations and agent instructions. | Earlier general-purpose alternative. Its repair quality on our files remains untested. [Ollama listing](https://ollama.com/library/phi4-mini:3.8b) |
| **Granite 4 3B** - `granite4:3b` | 2.1 GB | Small model supporting instructions, code-related tasks, and tool use. | Earlier alternative. The later Granite 4.2 3B model became the Granite candidate in the current comparison. They are different versions. [Ollama listing](https://ollama.com/library/granite4) |
| **Gemma 4 E2B** - `gemma4:e2b` | 4.6 GB for the llama.cpp package | Coding, reasoning, and agent capabilities, with image input available for possible future expansion. | More download and memory overhead than the smaller candidates. E2B means effective parameters, not total package size. The listing also offers a larger MLX package for Apple hardware. [Ollama listing](https://ollama.com/library/gemma4:e2b) |
| **Qwen3.5 4B** - `qwen3.5:4b` | 3.3 GB for the llama.cpp package | Newer candidate with published coding and agent evaluation results. | Alternative for later evaluation; not the selected model. Stronger than MiniCPM on some demanding agent benchmarks in the comparison below. Its listing also includes an Apple MLX package; that is not the Windows choice. [Ollama listing](https://ollama.com/library/qwen3.5:4b) |
| **Granite 4.2 3B** - `granite4.2:3b` | 2.2 GB | Newer Granite model supporting coding, tools, structured JSON output, and reasoning. | Current comparison candidate. Not evaluated locally. [Ollama listing](https://ollama.com/library/granite4.2:3b) |
| **MiniCPM5-2B** - `openbmb/minicpm5-2b` | 1.6 GB, Q4_K_M | Promising developer-reported generation and bug-fixing results in a small local package. | Earlier provisional recommendation, superseded by the user's selection of Qwen2.5-Coder 3B. It has not been downloaded by us, tested locally, or independently security-audited by us. [Ollama listing](https://ollama.com/openbmb/minicpm5-2b:latest) |

## Published results considered during earlier screening

These figures all come from one comparison in [OpenBMB's MiniCPM5-2B model card](https://huggingface.co/openbmb/MiniCPM5-2B#evaluation-results). OpenBMB states that the unmarked scores below were reproduced internally. These are developer-reported evaluation results, not independent certification and not measurements of the compressed Ollama packages on this laptop. Higher is better within each column.

| Model | LiveCodeBench v6 | SWE-bench Verified | SWE-bench Pro |
| --- | ---: | ---: | ---: |
| MiniCPM5-2B | 69.1 | 46.4 | 14.4 |
| Qwen3.5-4B | 56.4 | 33.6 | 28.2 |
| Granite 4.2 3B | 58.9 | 36.8 | 12.3 |
| Gemma 4 E2B | 42.9 | 2.0 | 0.0 |

[LiveCodeBench](https://livecodebench.github.io/) evaluates programming capabilities using contest problems. [SWE-bench Verified](https://www.swebench.com/) tests resolution of real repository issues. Benchmark results depend on the model, prompts, inference settings, available tools, and agent implementation. They are not a guarantee of success on our files. The Gemma result here is OpenBMB's reproduction; Google's separately published results use their own evaluation setup.

MiniCPM leads this table on LiveCodeBench and SWE-bench Verified; Qwen3.5 leads on SWE-bench Pro. This informed the earlier provisional shortlist. It does not establish a universal winner or prove superiority to models absent from this comparison, including the selected Qwen2.5-Coder 3B. The final choice prioritizes memory headroom, coding focus, and straightforward integration.

## Cost and license record

All nine models have downloadable local variants. Free download or local inference does not mean every model has identical license terms. Electricity, storage, and initial download data remain the user's costs; a hosted service may charge separately.

| Model or exact variant | License information checked |
| --- | --- |
| Qwen2.5-Coder 3B Instruct | The [publisher's model card](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct) identifies **Qwen Research**. Do not assume that the 3B variant has the same terms as other Qwen sizes. |
| Qwen2.5-Coder 7B | Confirm the license attached to the exact downloaded artifact before distribution or commercial deployment; the 3B license should not be extrapolated to it. [Package](https://ollama.com/library/qwen2.5-coder:7b) |
| DeepSeek-Coder 6.7B | [Custom DeepSeek model license](https://github.com/deepseek-ai/DeepSeek-Coder/blob/main/LICENSE-MODEL), including usage conditions. The repository code and model weights have separate licenses. |
| Phi-4 Mini | [MIT](https://huggingface.co/microsoft/Phi-4-mini-instruct). |
| Granite 4 3B | [Apache 2.0](https://ollama.com/library/granite4). |
| Gemma 4 E2B | [Apache 2.0](https://huggingface.co/google/gemma-4-E2B-it). |
| Qwen3.5 4B | [Apache 2.0](https://huggingface.co/Qwen/Qwen3.5-4B). |
| Granite 4.2 3B | [Apache 2.0](https://huggingface.co/ibm-granite/granite-4.2-3b). |
| MiniCPM5-2B | [Apache 2.0](https://huggingface.co/openbmb/MiniCPM5-2B#license). |

## Additional models screened during research

These were inspected or searched as possible alternatives, but were not presented as the final shortlist. Preliminary screening is not a measured rejection.

| Model | Depth of consideration and reason it did not advance |
| --- | --- |
| [Gemma 3 4B](https://ollama.com/library/gemma3/tags) | Earlier general-purpose candidate; package approximately 3.4 GB. Later research also examined Gemma 4. No head-to-head local test. |
| [StarCoder2 3B](https://ollama.com/library/starcoder2) | Approximately 1.7 GB coding model. The small base model is oriented toward code completion; the instruction-following variant identified in the listing is 15B. It was not advanced as the first conversational repair model. |
| [Granite Code 3B](https://ollama.com/library/granite-code/tags) | Preliminary search for a small coding specialist. No detailed comparison or local test was completed. Distinct from Granite 4 and Granite 4.2. |
| [Devstral Small 24B](https://arxiv.org/abs/2509.25193) | Coding-agent specialist considered during the broader search. Its 24B size makes it a poor first target for a 6 GB GPU; partial CPU execution would need separate assessment. |
| [Ministral 3 3B](https://ollama.com/library/ministral-3/tags) | Approximately 3.0 GB edge model. Screened as a compact option; no comparable repair result was established in this review. |
| [Nemotron 3.5 Bolt E4B](https://ollama.com/library/nemotron-3.5-bolt) | Screened as a newer coding and tool-use option. The checked Ollama listing shows approximately 7.2 GB for its llama.cpp E4B package, exceeding this GPU's total memory before runtime overhead. NVIDIA's separate 4 GB target-workload description should not be treated as the size or running requirement of this exact Ollama package. |

Other names appeared as size references or benchmark baselines: Qwen2.5-Coder 0.5B, 1.5B, 14B and 32B; DeepSeek-Coder 1.3B and 33B; Qwen3.5-2B; Gemma 4 E4B; LFM2.5-2.6B and LFM2.5-8B-A1B; and Nemotron-3-Nano-4B. We did not independently assess each of those as a proposed download. Their appearance in a source does not count as a recommendation.

## Safety and privacy findings

- A public publisher page, open license, or benchmark score does not certify a download's security. No MiniCPM package has been scanned or audited by us.
- [Ollama states](https://docs.ollama.com/faq#does-ollama-send-my-prompts-and-answers-back-to-ollamacom) that it does not receive prompts or responses when models run locally. Cloud models and connected applications require separate consideration.
- The [MiniCPM model card](https://huggingface.co/openbmb/MiniCPM5-2B#limitations-and-disclaimer) documents inaccurate outputs and susceptibility to manipulated prompts.
- Planned first-version behaviour: inspect selected files, propose a correction, validate syntax, show a diff, and preserve a backup when saving. Generated code or shell commands should be reviewed before execution. These are design proposals, not implemented features.
- Syntax validity does not prove correct behaviour, preservation of data, or absence of dangerous operations.

## Current decision and what remains unknown

**Decision made: Qwen2.5-Coder 3B Instruct, Q4_K_M.** The user selected this model for the first version, prioritizing memory headroom and compatibility with the 6 GB GPU. The reasons and initial evaluation settings are recorded at the top of this document.

No model has been benchmarked on this computer. Generation quality, repair quality, response speed, GPU memory use, and behaviour under the intended context settings remain unknown. The earlier Qwen partial download was removed; Ollama itself remained installed. No agent implementation code has been written.

The next proposed evaluation is a small set of Python generation tasks, Python syntax and behaviour repairs, and malformed JSON repairs. Compare correctness, unnecessary changes, response format, latency, and memory use. Explain the evaluation and its commands before running it. The user will download and install any selected model.
