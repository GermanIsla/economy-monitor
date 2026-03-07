#!/usr/bin/env python3
# run_pipeline.py
# Punto de entrada: ejecuta un pipeline manualmente desde la terminal

import sys
from db.engine import init_db

# Registro de pipelines disponibles
PIPELINES = {
    'treasury': 'pipelines.treasury_pipeline.TreasuryPipeline',
    'nfci': 'pipelines.nfci_pipeline.NFCIPipeline',
    'repo': 'pipelines.repo_pipeline.RepoPipeline',
    # Descomenta cuando estén implementados:
    # 'indices': 'pipelines.indices_pipeline.IndicesPipeline',
    # 'ecb': 'pipelines.ecb_pipeline.ECBPipeline',
}


def main():
    # Detectar flags
    from_staging = '--from-staging' in sys.argv
    full = '--full' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('--')]

    if not args or args[0] not in PIPELINES:
        print(f"\nEconomy Monitor — Ejecución manual de pipelines")
        print(f"{'='*55}")
        print(f"\nUso: python run_pipeline.py <pipeline> [opciones]\n")
        print(f"Pipelines disponibles:")
        for name in PIPELINES:
            print(f"  - {name}")
        print(f"\nOpciones:")
        print(f"  (sin opción)    Modo incremental: solo datos nuevos")
        print(f"  --full          Descarga completa de todo el histórico")
        print(f"  --from-staging  Re-procesar desde el último archivo de staging")
        print(f"                  (no descarga, usa los datos ya guardados)")
        print()
        sys.exit(1)

    pipeline_name = args[0]

    # Inicializar base de datos
    print("Inicializando base de datos...")
    init_db()

    # Importar dinámicamente el pipeline
    module_path, class_name = PIPELINES[pipeline_name].rsplit('.', 1)
    module = __import__(module_path, fromlist=[class_name])
    pipeline_class = getattr(module, class_name)

    # Determinar modo
    if from_staging:
        mode = "desde staging"
    elif full:
        mode = "descarga completa"
    else:
        mode = "incremental"

    print(f"\nEjecutando pipeline: {pipeline_name} ({mode})")
    print(f"{'='*55}\n")

    pipeline = pipeline_class()
    success = pipeline.run(from_staging=from_staging, full=full)

    if success:
        print(f"\n{'='*55}")
        print(f"Pipeline '{pipeline_name}' completado correctamente.")
    else:
        print(f"\n{'='*55}")
        print(f"Pipeline '{pipeline_name}' falló. Revisa los logs.")
        if not from_staging:
            print(f"Los datos crudos se guardaron en data/staging/")
            print(f"Puedes re-intentar: python run_pipeline.py {pipeline_name} --from-staging")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()