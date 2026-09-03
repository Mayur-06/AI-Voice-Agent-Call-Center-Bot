with open('app/websocket/handler.py', 'r') as f:
    lines = f.readlines()

# Fix lines 371-500: add 4 spaces to lines that are at 20 spaces (except elif lines themselves)
fixed_lines = []
for i, line in enumerate(lines):
    line_num = i + 1
    if line_num >= 371 and line_num <= 500:
        stripped = line.lstrip()
        spaces = len(line) - len(stripped)
        # If line is at 20 spaces and not an elif/if/try/except line, add 4 more spaces
        if spaces == 20 and not stripped.startswith(('elif ', 'if ', 'try:', 'except ', 'finally:')):
            fixed_lines.append('    ' + line)
            continue
    fixed_lines.append(line)

with open('app/websocket/handler.py', 'w') as f:
    f.writelines(fixed_lines)
print('Fixed indentation')
