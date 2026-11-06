# Example 01 — Catalog search, installments and a price lookup

> Simulated store clock: `2026-03-20T10:30:00` (America/Campo_Grande). Real Groq model `openai/gpt-oss-120b`; tool calls are shown in grey blocks.

**Cliente:** Oi! Quais opções de violões disponíveis custando até R$1000?

```
tools: search_products({"category": "Violões", "limit": 8, "max_price": 1000})
```

**Emi:** Oi! Seguem os violões que temos até **R$ 1.000** (preço de tabela):

1. **Tagima Memphis AC‑39 Nylon** – R$ 429,90 (à vista no PIX sai por R$ 408,40)  
2. **Rozini RC‑104 Nylon Estudante** – R$ 459,90 (PIX R$ 436,90)  
3. **Shelby SN‑100 Folk Aço** – R$ 549,00 (PIX R$ 521,55)  
4. **Giannini GF‑1R Aço Folk** – R$ 579,90 (PIX R$ 550,90)  
5. **Yamaha C40 Nylon** – R$ 599,90 (PIX R$ 569,90)  
6. **Giannini GN‑15 Nylon Cedr** – R$ 689,00 (PIX R$ 654,55)  
7. **Yamaha F310 Aço** – R$ 699,90 (PIX R$ 664,90)  
8. **Tagima Dallas Tuner Aço** – R$ 749,00 (PIX R$ 711,55)

Tem algum modelo que chamou mais a sua atenção ou quer saber mais detalhes (parcelamento, cores, etc.)? 🎸

**Cliente:** Me fala mais do Yamaha C40. Dá pra parcelar em quantas vezes?

```
tools: get_product({"name": "Yamaha C40"}) → payment_options({"amount": 599.9, "has_active_promotion": false})
```

**Emi:** **Yamaha C40 Nylon – Natural**  
- **Preço de tabela:** R$ 599,90  
- **À vista no PIX:** R$ 569,90  

**Parcelamento:** até **6x de R$ 99,98** sem juros (todas as parcelas são iguais).  

Quer saber mais sobre cores, garantia ou como garantir o seu? 🎶

**Cliente:** E o Takamine GD20, quanto custa?

```
tools: get_product({"name": "Takamine GD20"}) → payment_options({"amount": 2199, "has_active_promotion": false})
```

**Emi:** **Takamine GD20 Dreadnought – Natural**  
- **Preço de tabela:** R$ 2.199,00  
- **À vista no PIX:** R$ 2.089,05  

**Parcelamento:** até **12x de R$ 183,25** sem juros (todas as parcelas são iguais).  

É um violão dreadnought com tampo sólido em cedro, back e sides em sapele, ideal para quem busca timbre quente e projeção.  

Posso te ajudar com mais alguma informação ou abrir um chamado para o time entrar em contato? 🎸
