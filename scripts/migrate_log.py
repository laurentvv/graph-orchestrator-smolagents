import sys
import os
import re

# Add parent directory to path so we can import graph_orchestrator
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from graph_orchestrator.event_stream import EventStreamDB

def migrate_log_md():
    log_path = os.path.join(os.path.dirname(__file__), '..', 'log.md')
    
    if not os.path.exists(log_path):
        print(f"File {log_path} not found.")
        return

    db = EventStreamDB()
    
    with open(log_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    pattern = re.compile(r'^## \[([^\]]+)\]\s*(\w+)\s*\|\s*(.*)')
    
    current_date = None
    current_event_type = None
    current_message = []
    
    count = 0
    
    for line in lines:
        match = pattern.match(line)
        if match:
            # Save previous event
            if current_event_type is not None:
                msg = "\n".join(current_message).strip()
                # Insert to DuckDB. We'll use 'legacy' as run_id and 'system' as node
                db.log_event("legacy", "system", current_event_type, msg)
                count += 1
                
            current_date = match.group(1)
            current_event_type = match.group(2)
            current_message = [match.group(3)]
        elif current_event_type is not None:
            # Continue accumulating multi-line message
            current_message.append(line.rstrip())
            
    # Save the last event
    if current_event_type is not None:
        msg = "\n".join(current_message).strip()
        db.log_event("legacy", "system", current_event_type, msg)
        count += 1
        
    print(f"Successfully migrated {count} events from log.md to DuckDB (table run_event).")

if __name__ == "__main__":
    migrate_log_md()
