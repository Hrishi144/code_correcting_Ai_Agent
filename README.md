# Local coding assistant

A modular terminal coding assistant using local Ollama. It can answer questions,
inspect one explicitly selected Python/JSON/Java file, propose repairs, and generate
new code. File changes are previewed, validated, and saved only after approval.

## Run

Prerequisites: Python 3.10 or newer, a running Ollama server, and the selected
`qwen2.5-coder:7b` model installed locally. No additional Python packages are needed.
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
python -m ai_agent ask --model qwen2.5-coder:7b --timeout 180 "Explain Python dictionaries."
python -m ai_agent ask --context 8192 "Explain Python dictionaries."
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
does not choose the destination. `--model`, `--timeout`, and `--context` are available
after each subcommand. `--context` changes both Ollama's context setting and the
application's input budget; the default remains 4096. Larger contexts require more
memory and must be supported by your model. Context must exceed the 1024-token
output reserve plus the 256-token template reserve.

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
  There are no model-callable filesystem or shell tools. The opt-in checkout mode
  described below executes code, which itself can have filesystem or other side effects.

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

## Checking logic and following repair instructions

`fix` always asks the model to review syntax and logic with the smallest justified
repairs. A custom `--request` supplements that task; it does not replace it. Include
expected behavior and concrete examples, rather than only asking for comments.
The model may still miss errors or ignore instructions. Its explanation is marked
as unverified. By default the preview reports that behavior was not tested; opt-in
checkout mode reports the selected behavioral checks separately.

For existing Python files, `fix` compares syntax trees without executing code.
If a proposal changes only comments or formatting, the preview warns that it does
not demonstrate a logic repair. This is advisory: comment-only changes may be
intentional. A changed syntax tree does not prove correctness either.

For the shopping-cart example, an optional script checks eight behavioral cases:
the sample cart, default rates, an empty cart, full discount, nonpositive quantity,
negative price, invalid discount, and negative tax. Run it from this project folder:

```powershell
python examples/check_checkout.py "D:\code\Python\error.py"
```

**This explicit command executes the selected file, including its top-level code,
with your normal permissions. Review the file first.** It is not a sandbox or a
general-purpose verifier. The automated mode below uses the same fixed tests only
when explicitly enabled. The script
itself does not rewrite the selected file, but code you execute may have side effects.
The file must define `checkout(items, discount_percent=0, tax_percent=0)` returning
`subtotal`, `discount`, `tax`, and `total`. The sample cart must produce 500, 50, 45,
and 495 respectively with 10% discount and 10% tax.

Run the checks before and after a reviewed repair, using a copy if you want to keep
the original. Supply the failed expectations to `--request`, for example:

```powershell
python -m ai_agent fix --workspace "D:\code\Python" --file "error.py" --request "Quantity must be positive. Subtotal sums price times quantity. Discount is a percentage; tax applies after discount. The sample cart with 10% discount and tax must total 495. Comment each correction."
```

Other programs need tests based on their own requirements. Passing these eight
checkout checks covers those cases only; it is not proof of correctness for all inputs.

## Automate checkout repairs

For this standalone Python checkout example, combine test, repair, and retest in
one command. Ollama must be running with the selected model installed:

```powershell
python -m ai_agent fix --workspace "D:\code\Python" --file "error.py" --check checkout --allow-execution --max-attempts 3 --context 8192 --request "Add brief comments explaining each correction."
```

`--check checkout` selects the fixed eight-case suite and supplies its expected
behavior to the model. It is not a general test generator. Other programs and
languages are not supported by this automated checker. `--max-attempts` limits
model proposals to 1-5 (default 3); it does not include the original test run or
the final recheck before saving.

The example explicitly uses `--context 8192` to leave room for proposals that grow
during retries, such as when the model adds comments. The default 4096 context leaves
2816 for the conservative input estimate; 8192 leaves 6912 with the same reserves.
An input estimate of 3614 therefore fits the latter. This addresses the input limit,
not the accuracy of a repair. The application never grows context automatically.

**`--allow-execution` authorizes execution of the original and model-proposed
Python, including top-level code, before save approval.** Each run uses a temporary
copy in a separate Python process with a 10-second worker timeout and no terminal
input. This is not an OS sandbox: executed code has your normal permissions and
can access files, the network, or start other processes. The temporary directory,
isolated imports, and timeout do not contain those side effects. Use trusted code
in an environment suitable for executing model proposals. Test reports are not
tamper-proof against hostile code. File-save approval is separate from execution.

The workflow:

1. Validate the original syntax and run checkout tests if it parses.
2. If the original passes all eight checks, exit without calling the model or saving.
   Extra requests such as adding comments are not applied in that case; use
   `code --file` for an intentional edit to already-passing code.
3. Send the source, checkout requirements, and current failures to the model.
4. Syntax-check and test each proposal in a fresh temporary directory. Retry failed
   proposals with the latest source and failures, up to the attempt limit.
5. Stop on a passing proposal or when attempts are exhausted. Worker availability
   errors, malformed model replies, network errors, and context-budget errors stop
   the workflow; they are not automatically retried.
6. Show the final diff against the original. Failed/unavailable checks block saving.
   On success, ask for `save`, rerun the checkout checks, then use the existing
   original-file rechecks and backup procedure to save.

The application does not overwrite the selected file during these repair attempts.
Executed code can still have its own side effects. With redirected input/output,
explicitly enabled execution still occurs, but the resulting proposal is preview-only.
Subprocess output is discarded; failures are reported as compact test names and
limited exception summaries to preserve the model's input budget. Source is never
silently shortened. Large files, added comments, or requests can exceed the existing
context budget even in this mode. Python imports from neighboring project files are
not supported: only the selected standalone source is staged.

The tests verify specified checkout behavior, not comment quality or all possible
inputs. Passing them does not guarantee the model made every requested change.

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
  behavior.py       Opt-in timed execution of checkout candidates
  checkout_checks.py Fixed checkout expectations and worker reporting
  repair.py         Bounded test/repair/retest workflow
  changes.py        Diffs, change detection, backups, and approved saves
tests/              Automated tests and separate opt-in live model checks
```

The CLI reads a selected file through `Workspace`, obtains local validation,
and asks `CodingAssistant` for analysis or a proposal through `OllamaClient`.
Proposals include only explanation and content, never an executable tool call or
destination path. `ProposedChange` supplies the diff and validation result. After
interactive approval, `save_change` rechecks the file and commits the change.

Requests use Ollama's local `/api/chat` endpoint at `127.0.0.1:11434`, with streaming
disabled, a default 4096-token context setting (configurable with `--context`) and
a 1024-token output cap. The first
response may take longer while the model loads. Output appears when generation
finishes. The timeout controls socket operations, not a guaranteed total deadline.
The context guard counts UTF-8 bytes in message roles/content and the response
schema, plus the output allowance and a 256-token template reserve. Outer HTTP JSON
wrappers and escaping are not counted as model input. File content and diagnostics
are preserved in full. This is a conservative estimate, not exact model tokenization.
Rejections report the estimated input, available budget, and reserves. Large files,
long diagnostics, and verbose requests may still be rejected. Keep requests small.
There is no folder scanning, multi-file editing, or persistent conversation.
Execution and bounded repair retries are available only through the explicitly
enabled checkout mode; ordinary ask/inspect/fix/code commands do not run programs.

## Troubleshooting

- Connection error: open Ollama or run `ollama serve`, then retry.
- Missing model: run `ollama list` and choose an installed model with `--model`.
- Timeout: retry or increase `--timeout`.
- Output limit: request a smaller task; partial responses are explicitly marked.
- Context budget: the error suggests an explicit `--context` value large enough for
  the current estimate. Use it if your model and available memory support it, or
  select a smaller file or shorten the request. Retries can grow because they send
  the latest proposal. Content is not silently truncated, and more context does not
  guarantee a correct repair.
- Java dependency errors: this version checks standalone files using JDK libraries only.
- Preview only: run in an ordinary interactive terminal with input/output attached.

## Verify

```powershell
python -m unittest discover -s tests -v
```

The default suite uses simulated model responses and temporary sample files. It
tests access restrictions, invalid proposals, approval/rejection, backups,
intervening edits, terminal behavior, compiler isolation, and the automated checkout
loop using known test fixtures (not live model-generated programs). If `javac` is
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
