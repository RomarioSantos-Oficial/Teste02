"""
Script para gerar assets do instalador a partir do logo PNG.
Gera:
  - images/logo/Logo.bmp (164x314 para Inno Setup small image)
  - images/logo/Logo.ico (icone para o instalador)

Executar: python build/create_installer_assets.py
"""

from PIL import Image
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO_PNG = os.path.join(PROJECT_ROOT, "images", "logo", "Logo.png")

def create_bmp():
    """Cria BMP 164x314 para Inno Setup WizardSmallImageFile"""
    if not os.path.exists(LOGO_PNG):
        print(f"[AVISO] Logo nao encontrado: {LOGO_PNG}")
        return
    
    img = Image.open(LOGO_PNG)
    
    # Resize para 164x314 (Inno Setup small wizard image)
    # Converter RGBA para RGB (BMP nao suporta alpha)
    if img.mode == 'RGBA':
        # Criar fundo branco
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != 'RGB':
        img = img.convert('RGB')
    
    img = img.resize((164, 314), Image.LANCZOS)
    
    output_path = os.path.join(PROJECT_ROOT, "images", "logo", "Logo.bmp")
    img.save(output_path, 'BMP')
    print(f"[OK] BMP criado: {output_path}")

def create_ico():
    """Cria ICO a partir do logo PNG"""
    if not os.path.exists(LOGO_PNG):
        print(f"[AVISO] Logo nao encontrado: {LOGO_PNG}")
        return
    
    img = Image.open(LOGO_PNG).convert('RGBA')

    # Centralizar em uma tela quadrada preserva a proporção da marca. Salvar a
    # imagem-base em alta resolução permite que o Pillow gere todas as entradas
    # do ICO; usar a miniatura 16x16 como base criava apenas uma entrada.
    side = max(img.size)
    square = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    square.alpha_composite(img, ((side - img.width) // 2, (side - img.height) // 2))

    # Criar ICO real com múltiplos tamanhos para Explorer, atalhos e barra.
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    output_path = os.path.join(PROJECT_ROOT, "images", "logo", "Logo.ico")
    square.save(output_path, format='ICO', sizes=sizes)
    print(f"[OK] ICO criado: {output_path}")

if __name__ == "__main__":
    create_bmp()
    create_ico()
    print("\nAssets do instalador gerados com sucesso!")
