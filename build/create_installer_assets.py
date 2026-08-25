"""
Script para gerar assets do instalador a partir do logo PNG.
Gera:
  - images/logo/Logo.bmp (164x314 para Inno Setup small image)
  - images/logo/Logo.ico (icone para o instalador)

Executar: python build/create_installer_assets.py
"""

from PIL import Image, ImageChops
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
    """Cria um ICO multirresolução usando somente o símbolo da marca."""
    if not os.path.exists(LOGO_PNG):
        print(f"[AVISO] Logo nao encontrado: {LOGO_PNG}")
        return

    img = Image.open(LOGO_PNG).convert('RGBA')

    # O texto completo da marca ficava ilegível nos atalhos de 16/32 px. O
    # símbolo está na parte superior da arte; detectamos seus limites contra o
    # fundo claro e o transformamos em uma imagem transparente e quadrada.
    upper = img.crop((0, 0, img.width, round(img.height * 0.67)))
    background = Image.new('RGBA', upper.size, upper.getpixel((0, 0)))
    difference = ImageChops.difference(upper, background).convert('L')
    solid_mask = difference.point(lambda value: 255 if value > 24 else 0)
    bounds = solid_mask.getbbox()
    if bounds is None:
        raise RuntimeError("Não foi possível localizar o símbolo no logo.")

    symbol = upper.crop(bounds)
    symbol_difference = difference.crop(bounds)
    # O PNG original possui uma textura muito suave no fundo. Descartar essa
    # pequena variação evita pontos claros ao redor do símbolo nos atalhos.
    alpha = symbol_difference.point(
        lambda value: 0 if value <= 24 else min(255, (value - 24) * 6)
    )
    symbol.putalpha(alpha)

    side = max(symbol.size)
    padding = max(8, round(side * 0.08))
    square = Image.new(
        'RGBA',
        (side + 2 * padding, side + 2 * padding),
        (0, 0, 0, 0),
    )
    square.alpha_composite(
        symbol,
        (
            (square.width - symbol.width) // 2,
            (square.height - symbol.height) // 2,
        ),
    )

    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    output_path = os.path.join(PROJECT_ROOT, "images", "logo", "Logo.ico")
    square.save(output_path, format='ICO', sizes=sizes)
    print(f"[OK] ICO multirresolução criado: {output_path}")


if __name__ == "__main__":
    create_bmp()
    create_ico()
    print("\nAssets do instalador gerados com sucesso!")
