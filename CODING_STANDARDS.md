# Coding standards

Reviewers apply these rules to every diff in this repo. They are judgement calls; anything a test or script can check belongs in `tests/` instead.

## Safety guards

A **safety guard** is code that keeps secrets, home paths, unsafe paths or bad input out of files and output: an allowlist, an exemption, a redaction filter, a path check.

### Narrowing a guard ships with hostile-neighbour tests

A change that lets more input through a guard adds a test for a hostile neighbour of each newly allowed form: the same form with a shell separator after it (`|`, `;`, `&&`), with an empty or missing part (an empty host, no scheme), with an escaped or encoded value, and with an older sibling module that lacks the change. Each test proves the neighbour is still rejected.

Why: in #29 an exemption for `https://` URLs passed its tests and let `curl https://host/x|/home/<name>/bin/` through, and it broke the skill against an older `bmode`.

### Output that may hold user input is fixed text

An error or log line that could contain a user's argument, a file's content or an environment value prints fixed text and names the input by its role, such as an option name, not by its value. Filtering a message after the fact is not enough: the library may escape the value first, so the filter misses it.

Why: in #29 an `argparse` error was filtered for argument values, and a value ending in a newline was echoed in escaped form.
