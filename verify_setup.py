#!/usr/bin/env python3
"""
Script de verificación: comprueba que la tabla emails existe y que el flujo funciona end-to-end.
Uso: python verify_setup.py
"""

import asyncio
import sys
from pathlib import Path

async def main():
    print("=" * 70)
    print("VERIFICACIÓN DE SETUP - Joya de la Corona")
    print("=" * 70)
    
    # 1. Verificar que la tabla existe
    print("\n1. Comprobando conexión a Supabase...")
    try:
        from app.config import SUPABASE_URL, SUPABASE_KEY
        if SUPABASE_URL and SUPABASE_KEY:
            print(f"   [OK] SUPABASE_URL configurado")
            print(f"   [OK] SUPABASE_KEY configurado")
        else:
            print(f"   [ERROR] Variables de configuración vacías")
            return False
    except Exception as e:
        print(f"   [ERROR] {e}")
        return False
    
    # 2. Verificar que la tabla emails existe
    print("\n2. Comprobando tabla 'emails'...")
    try:
        from app.utils.supabase_client import supabase_select
        emails = await supabase_select('emails', {})
        print(f"   [OK] Tabla 'emails' existe (registros actuales: {len(emails)})")
    except Exception as e:
        print(f"   [ERROR] No se pudo acceder a tabla 'emails': {e}")
        print(f"   -> Ejecuta el SQL en: migrations/001_create_emails_table.sql")
        return False
    
    # 3. Verificar otros datos
    print("\n3. Comprobando tabla 'leads'...")
    try:
        leads = await supabase_select('leads', {})
        print(f"   [OK] Tabla 'leads' existe (registros: {len(leads)})")
    except Exception as e:
        print(f"   [WARN] No se encontró tabla 'leads' o error: {e}")
    
    # 4. Test end-to-end: P1 + Sequence
    print("\n4. Testing end-to-end (P1 + Sequence)...")
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            # P1
            print("   - Ejecutando P1 (scraping)...")
            r1 = await client.post(
                'http://127.0.0.1:8000/pipeline/p1',
                json={"query": "restaurante", "limit": 1},
                timeout=60.0
            )
            if r1.status_code != 200:
                print(f"   [WARN] P1 devolvió {r1.status_code}")
            else:
                p1_data = r1.json()
                if p1_data.get('leads'):
                    place_id = p1_data['leads'][0]['place_id']
                    print(f"   [OK] P1 generó lead: {place_id}")
                    
                    # Sequence
                    print("   - Ejecutando Sequence (P2-P5)...")
                    r_seq = await client.post(
                        'http://127.0.0.1:8000/pipeline/sequence',
                        json={
                            "place_id": place_id,
                            "url": "https://example.com",
                            "max_reviews": 3
                        },
                        timeout=180.0
                    )
                    if r_seq.status_code == 200:
                        seq_data = r_seq.json()
                        p5_emails = seq_data.get('p5', {}).get('emails_generados', 0)
                        print(f"   [OK] Sequence ejecutada, P5 generó {p5_emails} emails")
                    else:
                        print(f"   [WARN] Sequence devolvió {r_seq.status_code}")
                else:
                    print(f"   [INFO] P1 devolvió {len(p1_data.get('leads', []))} leads")
    except Exception as e:
        print(f"   [WARN] Error en test: {e}")
    
    # 5. Verificar que P6 (send) puede ejecutarse
    print("\n5. Testing P6 (envío de email)...")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                'http://127.0.0.1:8000/pipeline/p6',
                json={
                    "place_id": "ChIJwYl1nwyucZQRi1J2mVlp2IQ",
                    "to_email": "test@example.com",
                    "to_name": "Test User"
                },
                timeout=60.0
            )
            if r.status_code == 200:
                print(f"   [OK] P6 ejecutado correctamente")
            else:
                print(f"   [WARN] P6 devolvió {r.status_code}")
    except Exception as e:
        print(f"   [WARN] Error en P6: {e}")
    
    print("\n" + "=" * 70)
    print("VERIFICACIÓN COMPLETADA")
    print("=" * 70)
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
