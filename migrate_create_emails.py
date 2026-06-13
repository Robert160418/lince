#!/usr/bin/env python3
"""
Script para crear la tabla emails en Supabase.
Uso: python migrate_create_emails.py
"""

import asyncio
import httpx
from pathlib import Path
from app.config import SUPABASE_URL, SUPABASE_KEY

async def create_emails_table():
    """
    Lee el archivo SQL de migración y lo ejecuta en Supabase usando RPC.
    """
    sql_path = Path(__file__).parent / "migrations" / "001_create_emails_table.sql"
    
    if not sql_path.exists():
        print(f"Archivo no encontrado: {sql_path}")
        return False
    
    sql_content = sql_path.read_text(encoding="utf-8")
    print("SQL a ejecutar:")
    print(sql_content)
    print("\n" + "="*60)
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Error: SUPABASE_URL y SUPABASE_KEY no están configurados")
        return False
    
    # Usar el endpoint RPC para ejecutar SQL arbitrario
    # Nota: Supabase PostgREST no tiene un endpoint directo para ejecutar SQL arbitrario
    # La forma más segura es usar la API de funciones SQL o dashboard
    print("\n[OPCION 1] Ejecutar en Supabase Dashboard")
    print("1. Abre https://app.supabase.com/project/_/sql")
    print("2. Copia y pega el contenido del archivo migrations/001_create_emails_table.sql")
    print("3. Haz clic en 'Run'")
    
    print("\n[OPCION 2] Usar supabase CLI (si está instalado)")
    print("1. Instala: npm install -g supabase")
    print("2. Autentica: supabase login")
    print("3. Ejecuta: supabase db push")
    
    print("\n[VERIFICACION] Verificar conexión a Supabase...")
    try:
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient() as client:
            # Test connection
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/",
                headers=headers,
                timeout=10.0
            )
            if response.status_code in (200, 204):
                print("[OK] Conexión a Supabase OK")
            else:
                print(f"[ERROR] Respuesta inesperada: {response.status_code} {response.text[:200]}")
                return False
    except Exception as e:
        print(f"[ERROR] Error de conexión: {e}")
        return False
    
    print("\n[LISTO] Luego de crear la tabla, prueba: python -c \"from app.utils.supabase_client import supabase_select; import asyncio; asyncio.run(supabase_select('emails'))\"")
    return True

if __name__ == "__main__":
    result = asyncio.run(create_emails_table())
    exit(0 if result else 1)
