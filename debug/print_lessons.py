import duckdb

def print_lessons():
    conn = duckdb.connect("data/graph_orchestrator.db", read_only=True)
    query = """
        SELECT content, kind, created_at, status
        FROM claim
        WHERE kind IN ('insight', 'escalation')
          AND status = 'open'
        ORDER BY created_at DESC
        LIMIT 5
    """
    rows = conn.execute(query).fetchall()
    
    if not rows:
        print("Aucune leçon trouvée.")
        return
        
    for i, row in enumerate(rows):
        content, kind, created_at, status = row
        print(f"--- Leçon {i+1} [{kind}] ---")
        print(content)
        print()
    
    conn.close()

if __name__ == "__main__":
    print_lessons()
