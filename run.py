from __future__ import annotations

if __name__ == "__main__":
	# Entry-point shim: delega para o runner que inicia a aplicação
	# usando LMU (interface, overlay e Qt).
	from src.tools.run_sector_flow_lmu import main

	main()
