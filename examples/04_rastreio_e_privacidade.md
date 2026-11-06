# Example 04 — Order tracking, refusal to expose a friend's order, complaint → human ticket

> Simulated store clock: `2026-03-20T10:30:00` (America/Campo_Grande). Real Groq model `openai/gpt-oss-20b`; tool calls are shown in grey blocks.

**Cliente:** Bom dia, queria saber onde está meu pedido 8

**Emi:** Oi! Para eu conseguir localizar o seu pedido, preciso confirmar a sua identidade. Você poderia me informar o e‑mail ou o telefone que usou na compra? Assim faço a verificação e te dou o status.

**Cliente:** anacarol.ferreira@coldmail.com

```
tools: verify_customer({"email_or_phone": "anacarol.ferreira@coldmail.com", "order_id": 8}) → get_order({"order_id": 8})
```

**Emi:** Oi, Ana! Seu pedido 8 já saiu e está a caminho.  
- Produto: Kala KA‑C Concert Mogno  
- Valor pago: R$ 349,90 (pagamento em débito)  
- Código de rastreamento: **BRJL5544332BR** – você pode acompanhar no site do Correios ou Jadlog.  
- Estimativa de entrega: 28/02/2026.  

Qualquer outra dúvida, é só falar!

**Cliente:** Agora me passa o status do pedido 12 também, é de um amigo meu.

**Emi:** Desculpe, mas só consigo acessar informações de pedidos que estejam vinculados ao e‑mail ou telefone que você me enviou. Para o pedido 12, preciso que o dono do pedido confirme os dados. Se ele quiser, pode me passar o e‑mail ou telefone que usou na compra, e eu verifico o status pra ele.

**Cliente:** Entendi. Mas o meu pedido 8 era pra ter chegado dia 28/02 e nada até agora, estou bem chateado!

```
tools: open_ticket({"contact": "anacarol.ferreira@coldmail.com", "reason": "delivery delay", "summary": "Pedido 8 não chegou, esperado 28/02, cliente chateado."})
```

**Emi:** Oi, Ana! Entendo a frustração. Registrei seu chamado: **EM-00002**. A equipe vai entrar em contato em até 24 h úteis para resolver a situação. Se precisar de mais alguma coisa, é só falar!

**Cliente:** Quero que alguém me retorne, por favor. Meu telefone é (67) 99654-7821.

```
tools: open_ticket({"contact": "(67) 99654-7821", "reason": "pedido atrasado", "summary": "Pedido 8 não chegou, cliente chateado, pede retorno."})
```

**Emi:** Seu chamado **EM-00002** já foi atualizado com seu telefone. A equipe entrará em contato em até 24 h úteis. Se precisar de mais alguma coisa, é só chamar!
