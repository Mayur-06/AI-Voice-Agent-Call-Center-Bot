with open('app/websocket/handler.py', 'r') as f:
    content = f.read()

# Fix remaining elif blocks that are at wrong indentation
replacements = [
    ('                elif msg_type == "stop_call":',
     '                    elif msg_type == "stop_call":'),
    ('                elif msg_type == "stop_playback":',
     '                    elif msg_type == "stop_playback":'),
    ('                elif msg_type == "stop_listening":',
     '                    elif msg_type == "stop_listening":'),
    ('                elif msg_type == "transcript":',
     '                    elif msg_type == "transcript":'),
    ('                elif msg_type == "ping":',
     '                    elif msg_type == "ping":'),
]

for old, new in replacements:
    if old in content:
        content = content.replace(old, new)
        print(f'Fixed: {old.strip()}')
    else:
        print(f'Not found: {old.strip()}')

with open('app/websocket/handler.py', 'w') as f:
    f.write(content)
print('Done')
