# Modelo de Risco de Incêndio (Fire Hazard Score) - Relatório Executivo

## Metodologia e Parâmetros
O modelo de risco foi gerado através de uma matriz de regras baseada em índices espectrais e estrutura tridimensional do dossel:
- **Resolução Espacial:** 0.00250000 m² por pixel (dinâmico via gdal transform)
- **Área Total Analisada Geograficamente Relevante:** 137.7782 hectares

## Distribuição do Risco
| Score | Nível de Risco | Área (Hectares) | Regra Aplicada |
| :---: | :--- | :--- | :--- |
| 1 | Nulo (Cinza) | 0.0000 ha | ExG <= 5.0 |
| 2 | Baixo (Verde) | 73.0281 ha | ExG > 5.0 & VARI > 0.0 & CHM > 2.0m |
| 3 | Médio (Amarelo) | 18.0322 ha | ExG > 5.0 & VARI > 0.0 & CHM <= 2.0m |
| 4 | Alto (Laranja) | 32.3637 ha | ExG > 5.0 & VARI <= 0.0 & CHM > 1.0m |
| **5** | **CRÍTICO (Vermelho)** | **14.3541 ha** | **ExG > 5.0 & VARI <= 0.0 & CHM <= 1.0m** |

## Gráfico de Distribuição
![Distribuição de Risco de Incêndio](./fire_risk_distribution.png)

## Arquivos Gerenciais (COG)
O mapa resultante otimizado para a Web (Cloud Optimized GeoTIFF) encontra-se compilado na mesma rota sob nomeação protocolar.
- **Mapa de Calor:** `fire_hazard_score_cog.tif` (CTable Interno Aplicado)
