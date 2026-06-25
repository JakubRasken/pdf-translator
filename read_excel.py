import pandas as pd
import json

excel_path = r"C:\Users\jakub\Downloads\VIVAX_prelozit\SERVICE MANUAL\HR_ENG_Klima katalog 2026_Tekstovi - CZ.xlsx"
df = pd.read_excel(excel_path)
df = df.dropna(subset=['ENG', 'CZ'])

matches = []
for idx, row in df.iterrows():
    matches.append({"ENG": str(row['ENG']).strip(), "CZ": str(row['CZ']).strip()})

with open('all_excel.json', 'w', encoding='utf-8') as f:
    json.dump(matches, f, ensure_ascii=False, indent=2)
