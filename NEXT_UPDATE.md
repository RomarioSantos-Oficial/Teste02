# Próxima atualização

## Correção confirmada

- [x] Preservar o idioma escolhido no aplicativo durante uma atualização. O instalador cria `%LOCALAPPDATA%\SectorFlow\language.json` somente quando o arquivo ainda não existe, sem substituir a preferência atual do usuário.

## Alterações aprovadas e implementadas

- [x] STR: mover a coluna de tempo de PIT para imediatamente depois do nome do piloto e antes da marca/logo do carro.
- [x] STR: manter sempre a marca/logo do carro na coluna `MAR` e mover a bandeira de chegada para a coluna automática `STS`, que mostra chegada, garagem, pit, DNF, DQ, volta inválida, bandeira amarela e punições.
- [x] STR: ao aumentar a largura do nome, deslocar PIT e todas as colunas seguintes pela mesma quantidade; nas linhas sem tempo de PIT visível, emprestar o espaço vazio do PIT ao nome do piloto.
- [x] Instalador: usar ícone multirresolução com o símbolo ampliado, oferecer somente o atalho opcional da Área de Trabalho e não criar atalhos no Menu Iniciar.
