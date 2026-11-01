# Local coding assistant

A modular terminal coding assistant using local Ollama. It can answer questions,
inspect one explicitly selected Python/JSON/Java file, propose repairs, and generate
new code. File changes are previewed, validated, and saved only after approval.

## Run

Prerequisites: Python 3.10 or newer, a running Ollama server, and the selected
`qwen2.5-coder:3b` model installed locally. No additional Python packages are needed.
Java validation also requires `javac` on PATH (verified here with JDK 25.0.3).
Downloads and installations are managed by the user. The application does not
start Ollama, install models, or install a JDK.

From this project folder in PowerShell:

```powershell
python -m ai_agent ask "Write a Python function that checks whether a number is even."
```

To enter a request at a terminal prompt:

```powershell
python -m ai_agent
```

Each invocation handles one independent request and exits; there is no conversation
history. The original `python -m ai_agent "question"` form still works. For `ask`,
standard input also supports piped, multiline requests. A bare reserved command
word such as `fix` is interpreted as a subcommand; use `ask "fix"` to ask about it.

```powershell
python -m ai_agent ask --model qwen2.5-coder:3b --timeout 180 "Explain Python dictionaries."
python -m ai_agent --help
```

## Inspect, correct, and create files

Replace the example filenames below with your own selected files. The workspace
and destination's parent directory must already exist. Paths are relative to the
workspace, or absolute paths inside it. The application does not scan the folder.

Read a Python file, report its syntax-check result, and ask the model to analyze it:

```powershell
python -m ai_agent inspect --workspace "D:\code\Ai_agent" --file "example.py"
```

Propose a correction. Use `--request` for a traceback, observed problem, or expected
behavior; omitting it asks for the smallest necessary correction:

```powershell
python -m ai_agent fix --workspace "D:\code\Ai_agent" --file "example.py"
python -m ai_agent fix --workspace "D:\code\Ai_agent" --file "data.json"
python -m ai_agent fix --workspace "D:\code\Ai_agent" --file "Hello.java" --request "Fix the missing semicolon."
```

Generate a new file with `--output`, or edit an existing one with `--file`:

```powershell
python -m ai_agent code --workspace "D:\code\Ai_agent" --output "calculator.py" --request "Create add and subtract functions."
python -m ai_agent code --workspace "D:\code\Ai_agent" --output "Hello.java" --request "Create public class Hello with a main method that prints Hello."
python -m ai_agent code --workspace "D:\code\Ai_agent" --file "calculator.py" --request "Add a multiply function."
```

`--output` refuses an existing file. `--file` requires an existing file. The model
does not choose the destination. `--model` and `--timeout` are available after each
subcommand.

## Review and saving

1. Check the selected absolute path and original validation result.
2. Read the model's explanation, proposed validation result, and unified diff.
   Lines starting with `-` are removed and `+` are added. Terminal control
   characters are shown as escapes instead of being interpreted.
3. If validation passes, type exactly `save` at the interactive approval prompt.
   Enter or any other answer rejects the change. Ctrl+C cancels.
4. Before committing, the application revalidates the proposal and checks that
   the original has not changed. Existing files receive a byte-for-byte backup in
   `.ai_agent_backups` under the workspace; its path is printed after saving.

`inspect` never saves. Failed or unavailable validation blocks saving. Invalid or
truncated model proposals cannot be saved. With redirected input or output, file
commands display previews only; there is no automatic `--yes` option. Rejected
changes do not create backups. Failed commits may leave a backup for recovery.
Existing UTF-8 BOMs and consistent CRLF line endings are preserved. New files use
UTF-8 and LF. Backups can contain sensitive source data; manage them as source files.

## File access and validation

- Only the explicitly selected `.py`, `.json`, or `.java` file is read. Files must
  be UTF-8 (a UTF-8 BOM is accepted), nonbinary, and at most 16 KiB.
- Requests must also fit a conservative context budget, which is normally much
  smaller than the read limit. Oversized requests are rejected without trimming.
- Paths outside the selected workspace, hidden paths, `node_modules`, `venv`,
  `__pycache__`, symbolic links, junctions, reparse points, and hard-linked files
  are rejected. Protected folders cannot be selected as a workspace to bypass
  these checks. The app itself creates its hidden backup/staging files.
- File contents and model output cannot authorize additional reads or writes.
  There are no model-callable filesystem or shell tools.

| Language | Check | Limit |
| --- | --- | --- |
| Python | Compile source in memory without executing or importing it | Syntax only; no runtime or logical correctness check |
| JSON | Parse JSON, rejecting nonstandard NaN/Infinity constants | No application schema or business-rule verification |
| Java | Compile a temporary copy with `javac -proc:none`, isolated dependency paths, and a 20-second timeout | Only the selected file and JDK libraries; no program execution |

Java compiler output and temporary class files stay outside the project in a
temporary directory that is cleaned up afterward. Annotation processing is
disabled and inherited compiler/JVM option variables are removed. Missing project
classes or external libraries can cause compilation failure; multi-file projects
and dependency resolution are not implemented. The installed JDK determines the
Java language version checked.

Passing these checks does not establish correct behavior. Model explanations can
be wrong; review the proposed change. Path checks and save rechecks are application
controls, not an OS sandbox or a cross-process file lock. There remains a narrow
race between the final file check and replacement if another process changes it.

## Outputs and status

Answers, analysis, validation results, diffs, and save results go to standard output.
Progress and handled errors go to standard error. An interactive approval prompt is
also displayed in the terminal.

- `0`: completed request or preview, rejected save, unchanged valid proposal, or help.
- `1`: handled failure, failed/unavailable validation, or truncated response.
- `2`: invalid command-line usage.
- `130`: cancellation during the main workflow.

A successful preview does not mean a file was saved; read the printed result.

## Architecture

```text
ai_agent/
  __main__.py       Module entry point
  cli.py            Commands, previews, approval prompts, and exit codes
  assistant.py      Analysis and structured code proposals
  config.py         Model settings, supported file types, and limits
  ollama_client.py  Local HTTP requests, context budget, and response handling
  workspace.py      Path restrictions and selected-file snapshots
  validation.py     Python/JSON checks and isolated Java compilation
  changes.py        Diffs, change detection, backups, and approved saves
tests/              Automated tests and separate opt-in live model checks
```

The CLI reads a selected file through `Workspace`, obtains local validation,
and asks `CodingAssistant` for analysis or a proposal through `OllamaClient`.
Proposals include only explanation and content, never an executable tool call or
destination path. `ProposedChange` supplies the diff and validation result. After
interactive approval, `save_change` rechecks the file and commits the change.

Requests use Ollama's local `/api/chat` endpoint at `127.0.0.1:11434`, with streaming
disabled, a 4096-token context setting and a 1024-token output cap. The first
response may take longer while the model loads. Output appears when generation
finishes. The timeout controls socket operations, not a guaranteed total deadline.
The context guard counts UTF-8 bytes in message roles/content and the response
schema, plus the output allowance and a 256-token template reserve. Outer HTTP JSON
wrappers and escaping are not counted as model input. File content and diagnostics
are preserved in full. This is a conservative estimate, not exact model tokenization.
Rejections report the estimated input, available budget, and reserves. Large files,
long diagnostics, and verbose requests may still be rejected. Keep requests small.
There is no automatic retry, folder scanning,
multi-file editing, persistent conversation, or execution of generated programs.

## Troubleshooting

- Connection error: open Ollama or run `ollama serve`, then retry.
- Missing model: run `ollama list` and choose an installed model with `--model`.
- Timeout: retry or increase `--timeout`.
- Output limit: request a smaller task; partial responses are explicitly marked.
- Context budget: select a smaller file or shorten the request. Content is not silently truncated.
- Java dependency errors: this version checks standalone files using JDK libraries only.
- Preview only: run in an ordinary interactive terminal with input/output attached.

## Verify

```powershell
python -m unittest discover -s tests -v
```

The default suite uses simulated model responses and temporary sample files. It
tests access restrictions, invalid proposals, approval/rejection, backups,
intervening edits, terminal behavior, and compiler isolation. If `javac` is
installed, it also compiles valid, invalid, and dependency-missing Java samples.
Temporary-directory access must be permitted by the environment running the tests.

Opt-in live checks contact the default local model for seven requests covering
inspection, repairs, and generation in all three languages:

```powershell
python -m unittest discover -s tests -p live_smoke.py -v
```

Live checks use temporary samples, do not execute generated programs, and do not
save model proposals to project files. These examples do not establish general
repair accuracy.

References: [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs),
[Java 25 javac options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).
