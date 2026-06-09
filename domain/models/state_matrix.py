class StateMatrix:
    def __init__(self, ids, taxa_names, state_columns, rows, source_path):
        self.ids = ids
        self.taxa_names = taxa_names
        self.state_columns = state_columns
        self.rows = rows
        self.source_path = source_path

    def row_count(self):
        return len(self.rows)

    def column_count(self):
        return 2 + len(self.state_columns)

    def preview_rows(self, limit=50):
        return self.rows[:limit]