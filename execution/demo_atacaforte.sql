-- ============================================
-- ⚠️  ATENÇÃO — APENAS PARA DEMONSTRAÇÃO ⚠️
-- NÃO RODAR EM PRODUÇÃO!
-- Este arquivo apaga todos os dados reais e
-- insere dados falsos (produtos, feedbacks, preços).
-- Use SOMENTE para apresentar o sistema a clientes.
-- Para produção, use o arquivo seed.sql.
-- ============================================
-- DEMO DATA - ATACAFORTE SUPERMERCADOS
-- Horário: 08:00 às 19:30
-- ============================================
-- Limpar dados anteriores (preserva estrutura)
DELETE FROM lista_espera;
DELETE FROM notificacoes;
DELETE FROM feedbacks;
DELETE FROM produtos;
DELETE FROM config;
-- ======================================
-- 1. CONFIGURAÇÃO - Categorias e Lojas
-- ======================================
INSERT INTO config (type, name, color)
VALUES ('category', 'Atendimento', '#3b82f6'),
    ('category', 'Fila', '#f59e0b'),
    ('category', 'Hortifrúti', '#10b981'),
    ('category', 'Padaria', '#f97316'),
    ('category', 'Açougue', '#ef4444'),
    ('category', 'Limpeza', '#8b5cf6'),
    ('category', 'Preço', '#ec4899'),
    ('category', 'Estacionamento', '#6366f1'),
    ('category', 'Geral', '#64748b');
INSERT INTO config (type, name)
VALUES ('region', 'Matriz'),
    ('region', 'Filial Centro'),
    ('region', 'Filial Norte');
-- ======================================
-- 2. PRODUTOS - Catálogo completo Atacaforte
-- ======================================
-- AÇOUGUE
INSERT INTO produtos (
        nome,
        categoria,
        preco,
        preco_promo,
        em_estoque,
        unidade
    )
VALUES (
        'Picanha Bovina',
        'Açougue',
        69.90,
        59.90,
        true,
        'kg'
    ),
    (
        'Contra Filé',
        'Açougue',
        49.90,
        42.90,
        true,
        'kg'
    ),
    ('Alcatra', 'Açougue', 52.90, NULL, true, 'kg'),
    ('Fraldinha', 'Açougue', 44.90, 39.90, true, 'kg'),
    (
        'Costela Bovina',
        'Açougue',
        34.90,
        29.90,
        true,
        'kg'
    ),
    (
        'Peito de Frango',
        'Açougue',
        16.90,
        13.90,
        true,
        'kg'
    ),
    (
        'Coxa e Sobrecoxa',
        'Açougue',
        12.90,
        10.90,
        true,
        'kg'
    ),
    (
        'Linguiça Toscana',
        'Açougue',
        19.90,
        16.90,
        true,
        'kg'
    ),
    (
        'Carne Moída',
        'Açougue',
        29.90,
        24.90,
        true,
        'kg'
    ),
    (
        'Bisteca Suína',
        'Açougue',
        22.90,
        NULL,
        true,
        'kg'
    ),
    (
        'Filé de Tilápia',
        'Açougue',
        39.90,
        34.90,
        true,
        'kg'
    ),
    -- HORTIFRÚTI
    (
        'Banana Prata',
        'Hortifrúti',
        5.49,
        3.99,
        true,
        'kg'
    ),
    (
        'Maçã Fuji',
        'Hortifrúti',
        9.90,
        7.90,
        true,
        'kg'
    ),
    (
        'Laranja Pera',
        'Hortifrúti',
        4.99,
        3.49,
        true,
        'kg'
    ),
    (
        'Tomate Italiano',
        'Hortifrúti',
        8.90,
        6.90,
        true,
        'kg'
    ),
    (
        'Batata Inglesa',
        'Hortifrúti',
        5.90,
        4.49,
        true,
        'kg'
    ),
    ('Cebola', 'Hortifrúti', 4.90, 3.90, true, 'kg'),
    ('Alho', 'Hortifrúti', 39.90, NULL, true, 'kg'),
    (
        'Alface Crespa',
        'Hortifrúti',
        3.49,
        2.49,
        true,
        'un'
    ),
    (
        'Limão Taiti',
        'Hortifrúti',
        6.90,
        4.90,
        true,
        'kg'
    ),
    ('Melancia', 'Hortifrúti', 2.49, 1.99, true, 'kg'),
    ('Abacaxi', 'Hortifrúti', 6.90, 4.90, true, 'un'),
    (
        'Mamão Papaya',
        'Hortifrúti',
        7.90,
        NULL,
        true,
        'un'
    ),
    ('Cenoura', 'Hortifrúti', 5.90, NULL, true, 'kg'),
    -- PADARIA
    (
        'Pão Francês',
        'Padaria',
        16.90,
        14.90,
        true,
        'kg'
    ),
    (
        'Pão de Queijo',
        'Padaria',
        39.90,
        34.90,
        true,
        'kg'
    ),
    (
        'Bolo de Chocolate',
        'Padaria',
        22.90,
        NULL,
        true,
        'un'
    ),
    ('Croissant', 'Padaria', 4.90, 3.90, true, 'un'),
    (
        'Pão Integral',
        'Padaria',
        8.90,
        NULL,
        true,
        'un'
    ),
    ('Sonho', 'Padaria', 5.90, NULL, true, 'un'),
    -- LATICÍNIOS
    (
        'Leite Integral 1L',
        'Laticínios',
        5.49,
        4.79,
        true,
        'un'
    ),
    (
        'Queijo Mussarela',
        'Laticínios',
        44.90,
        39.90,
        true,
        'kg'
    ),
    (
        'Iogurte Natural',
        'Laticínios',
        6.90,
        5.49,
        true,
        'un'
    ),
    (
        'Manteiga 200g',
        'Laticínios',
        8.90,
        7.49,
        true,
        'un'
    ),
    (
        'Requeijão 200g',
        'Laticínios',
        7.90,
        6.49,
        true,
        'un'
    ),
    (
        'Queijo Prato',
        'Laticínios',
        49.90,
        44.90,
        true,
        'kg'
    ),
    (
        'Cream Cheese 150g',
        'Laticínios',
        9.90,
        NULL,
        true,
        'un'
    ),
    -- BEBIDAS
    (
        'Coca-Cola 2L',
        'Bebidas',
        9.90,
        7.99,
        true,
        'un'
    ),
    (
        'Guaraná Antarctica 2L',
        'Bebidas',
        8.90,
        6.99,
        true,
        'un'
    ),
    (
        'Água Mineral 500ml',
        'Bebidas',
        2.49,
        NULL,
        true,
        'un'
    ),
    (
        'Suco Del Valle 1L',
        'Bebidas',
        8.90,
        6.90,
        true,
        'un'
    ),
    (
        'Cerveja Brahma 350ml',
        'Bebidas',
        3.99,
        2.99,
        true,
        'un'
    ),
    (
        'Cerveja Heineken 350ml',
        'Bebidas',
        5.99,
        4.49,
        true,
        'un'
    ),
    (
        'Café Melitta 500g',
        'Bebidas',
        18.90,
        15.90,
        true,
        'un'
    ),
    (
        'Café Premium 500g',
        'Bebidas',
        29.90,
        24.90,
        true,
        'un'
    ),
    -- MERCEARIA
    (
        'Arroz 5kg',
        'Mercearia',
        27.90,
        22.90,
        true,
        'un'
    ),
    (
        'Feijão Carioca 1kg',
        'Mercearia',
        8.90,
        6.90,
        true,
        'un'
    ),
    (
        'Açúcar 1kg',
        'Mercearia',
        5.49,
        4.49,
        true,
        'un'
    ),
    (
        'Óleo de Soja 900ml',
        'Mercearia',
        7.90,
        6.49,
        true,
        'un'
    ),
    (
        'Macarrão Espaguete 500g',
        'Mercearia',
        4.90,
        3.90,
        true,
        'un'
    ),
    (
        'Molho de Tomate 340g',
        'Mercearia',
        3.90,
        2.99,
        true,
        'un'
    ),
    (
        'Farinha de Trigo 1kg',
        'Mercearia',
        5.90,
        NULL,
        true,
        'un'
    ),
    ('Sal 1kg', 'Mercearia', 2.49, NULL, true, 'un'),
    (
        'Azeite Extra Virgem 500ml',
        'Mercearia',
        24.90,
        19.90,
        true,
        'un'
    ),
    (
        'Biscoito Maria 200g',
        'Mercearia',
        3.90,
        NULL,
        true,
        'un'
    ),
    -- LIMPEZA
    (
        'Detergente 500ml',
        'Limpeza',
        2.99,
        1.99,
        true,
        'un'
    ),
    (
        'Água Sanitária 1L',
        'Limpeza',
        4.90,
        3.49,
        true,
        'un'
    ),
    (
        'Sabão em Pó 1kg',
        'Limpeza',
        12.90,
        9.90,
        true,
        'un'
    ),
    (
        'Desinfetante 500ml',
        'Limpeza',
        5.90,
        4.49,
        true,
        'un'
    ),
    (
        'Papel Higiênico 12un',
        'Limpeza',
        14.90,
        11.90,
        true,
        'un'
    ),
    (
        'Esponja de Aço 8un',
        'Limpeza',
        3.90,
        NULL,
        true,
        'un'
    ),
    (
        'Amaciante 2L',
        'Limpeza',
        12.90,
        9.90,
        true,
        'un'
    ),
    -- CONGELADOS
    (
        'Pizza Congelada',
        'Congelados',
        14.90,
        11.90,
        true,
        'un'
    ),
    (
        'Hambúrguer 672g',
        'Congelados',
        16.90,
        NULL,
        true,
        'un'
    ),
    (
        'Nuggets 300g',
        'Congelados',
        14.90,
        12.90,
        true,
        'un'
    ),
    (
        'Sorvete 1.5L',
        'Congelados',
        19.90,
        15.90,
        true,
        'un'
    ),
    (
        'Lasanha Congelada',
        'Congelados',
        16.90,
        13.90,
        true,
        'un'
    ),
    -- HIGIENE
    (
        'Sabonete 90g',
        'Higiene',
        2.49,
        NULL,
        true,
        'un'
    ),
    (
        'Shampoo 350ml',
        'Higiene',
        14.90,
        11.90,
        true,
        'un'
    ),
    (
        'Creme Dental 90g',
        'Higiene',
        5.90,
        4.49,
        true,
        'un'
    ),
    (
        'Desodorante Roll-on',
        'Higiene',
        9.90,
        7.90,
        true,
        'un'
    ),
    (
        'Fralda Descartável P 40un',
        'Higiene',
        39.90,
        34.90,
        true,
        'un'
    ),
    -- FRIOS
    (
        'Presunto Cozido',
        'Frios',
        32.90,
        27.90,
        true,
        'kg'
    ),
    ('Mortadela', 'Frios', 14.90, 12.90, true, 'kg'),
    (
        'Salame Italiano',
        'Frios',
        54.90,
        NULL,
        true,
        'kg'
    ),
    (
        'Peito de Peru',
        'Frios',
        42.90,
        37.90,
        true,
        'kg'
    );
-- ======================================
-- 3. FEEDBACKS REALISTAS - últimas 48h
-- ======================================
-- Feedbacks POSITIVOS
INSERT INTO feedbacks (
        sender,
        name,
        message,
        timestamp,
        category,
        region,
        urgency,
        sentiment,
        loja,
        status
    )
VALUES (
        '5544999110001@s.whatsapp.net',
        'Maria Silva',
        'O açougue do Atacaforte é o melhor da região! A carne é sempre fresquinha e o açougueiro muito atencioso, cortou do jeitinho que pedi. Nota 10!',
        NOW() - INTERVAL '2 hours',
        'Açougue',
        'Caixas',
        'Positivo',
        'Positivo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110002@s.whatsapp.net',
        'Carlos Oliveira',
        'Parabéns pela padaria, o pão francês sai quente 3 vezes ao dia! Melhor pão da cidade. Sempre fresquinho.',
        NOW() - INTERVAL '5 hours',
        'Padaria',
        'Padaria',
        'Positivo',
        'Positivo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110003@s.whatsapp.net',
        'Ana Costa',
        'Adorei as promoções de hortifrúti! Banana a 3,99 o kg é um roubo! No bom sentido rsrs. Vou voltar amanhã.',
        NOW() - INTERVAL '8 hours',
        'Hortifrúti',
        'Hortifrúti',
        'Positivo',
        'Positivo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110004@s.whatsapp.net',
        'Roberto Santos',
        'Funcionários muito educados, diferente de outros mercados. A moça do caixa 3 é super simpática e rápida.',
        NOW() - INTERVAL '10 hours',
        'Atendimento',
        'Caixas',
        'Positivo',
        'Positivo',
        'Matriz',
        'resolvido'
    ),
    -- Feedbacks NEUTROS
    (
        '5544999110005@s.whatsapp.net',
        'Fernanda Lima',
        'Vocês vendem ração para cachorro? Procurei por toda loja e não encontrei.',
        NOW() - INTERVAL '3 hours',
        'Geral',
        'Geral',
        'Neutro',
        'Neutro',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110006@s.whatsapp.net',
        'Pedro Souza',
        'Qual o horário de funcionamento da padaria? Cheguei às 7 e estava fechado.',
        NOW() - INTERVAL '14 hours',
        'Padaria',
        'Padaria',
        'Neutro',
        'Neutro',
        'Matriz',
        'resolvido'
    ),
    (
        '5544999110007@s.whatsapp.net',
        'Juliana Mendes',
        'Existe estacionamento para motos? Vi que tem bastante vaga de carro mas não achei pra moto.',
        NOW() - INTERVAL '18 hours',
        'Estacionamento',
        'Estacionamento',
        'Neutro',
        'Neutro',
        'Matriz',
        'aberto'
    ),
    -- Feedbacks URGENTES
    (
        '5544999110008@s.whatsapp.net',
        'Marcos Pereira',
        'A fila do caixa está enorme, faz 25 minutos que estou esperando e só tem 2 caixas abertos. Péssimo!',
        NOW() - INTERVAL '1 hour',
        'Fila',
        'Caixas',
        'Urgente',
        'Negativo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110009@s.whatsapp.net',
        'Tatiana Rodrigues',
        'O estacionamento está uma loucura, não tem ninguém organizando e quase bati meu carro. Precisam colocar alguém ali urgente!',
        NOW() - INTERVAL '4 hours',
        'Estacionamento',
        'Estacionamento',
        'Urgente',
        'Negativo',
        'Matriz',
        'em_andamento'
    ),
    (
        '5544999110010@s.whatsapp.net',
        'João Almeida',
        'Comprei carne moída ontem e quando cheguei em casa tinha cheiro estranho. Fiquei muito insatisfeito.

[Atualização]: Tentei trocar mas o funcionário disse que não pode. Quero falar com o gerente.',
        NOW() - INTERVAL '6 hours',
        'Açougue',
        'Açougue',
        'Urgente',
        'Negativo',
        'Matriz',
        'em_andamento'
    ),
    -- Feedbacks CRÍTICOS 
    (
        '5544999110011@s.whatsapp.net',
        'Luciana Ferreira',
        'ABSURDO! Comprei um iogurte VENCIDO! Data de validade era de semana passada. Isso é crime! Vou no Procon!',
        NOW() - INTERVAL '30 minutes',
        'Preço',
        'Geral',
        'Critico',
        'Negativo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110012@s.whatsapp.net',
        'Ricardo Gomes',
        'Escorreguei no corredor de limpeza porque tinha água no chão e nenhuma sinalização. Machiquei meu joelho. Absurdo!',
        NOW() - INTERVAL '2 hours',
        'Limpeza',
        'Limpeza',
        'Critico',
        'Negativo',
        'Matriz',
        'aberto'
    ),
    -- Feedbacks variados 
    (
        '5544999110013@s.whatsapp.net',
        'Camila Nascimento',
        'Meus parabéns pelas promoções dessa semana! Economizei mais de 80 reais no rancho do mês inteiro.',
        NOW() - INTERVAL '12 hours',
        'Preço',
        'Geral',
        'Positivo',
        'Positivo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110014@s.whatsapp.net',
        'André Barbosa',
        'O ar condicionado não está funcionando na loja. Está muito quente, difícil fazer compras assim.',
        NOW() - INTERVAL '3 hours',
        'Geral',
        'Geral',
        'Urgente',
        'Negativo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110015@s.whatsapp.net',
        'Patrícia Dias',
        'A seção de hortifrúti está excelente! Sempre bem organizada e com frutas de qualidade. O rapaz que trabalha lá é muito prestativo.',
        NOW() - INTERVAL '16 hours',
        'Hortifrúti',
        'Hortifrúti',
        'Positivo',
        'Positivo',
        'Matriz',
        'resolvido'
    ),
    (
        '5544999110016@s.whatsapp.net',
        'Diego Martins',
        'O preço do arroz aumentou muito de uma semana pra outra, de 19,90 foi pra 27,90. Absurdo esse aumento.',
        NOW() - INTERVAL '7 hours',
        'Preço',
        'Mercearia',
        'Urgente',
        'Negativo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110017@s.whatsapp.net',
        'Sandra Moreira',
        'Poderiam colocar mais opções de produtos sem glúten e sem lactose. Tenho alergia e não encontro quase nada.',
        NOW() - INTERVAL '20 hours',
        'Geral',
        'Mercearia',
        'Neutro',
        'Neutro',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110018@s.whatsapp.net',
        'Felipe Costa',
        'A padaria do Atacaforte é sensacional! Comprei o bolo de chocolate ontem pro aniversário da minha filha e foi sucesso total!',
        NOW() - INTERVAL '22 hours',
        'Padaria',
        'Padaria',
        'Positivo',
        'Positivo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110019@s.whatsapp.net',
        'Mariana Ribeiro',
        'Falta sinalização nos corredores. Difícil encontrar os produtos, principalmente pra quem vem pela primeira vez.',
        NOW() - INTERVAL '24 hours',
        'Geral',
        'Geral',
        'Neutro',
        'Neutro',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110020@s.whatsapp.net',
        'Lucas Ferreira',
        'Ótimo custo benefício nas carnes. A picanha de 59,90 o kg é muito boa. Em outros mercados não sai por menos de 75.',
        NOW() - INTERVAL '9 hours',
        'Açougue',
        'Açougue',
        'Positivo',
        'Positivo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110021@s.whatsapp.net',
        'Gabriela Santos',
        'O caixa rápido não estava funcionando e tinha que ir pro caixa normal com apenas 3 itens. Perdi muito tempo.',
        NOW() - INTERVAL '5 hours',
        'Fila',
        'Caixas',
        'Urgente',
        'Negativo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110022@s.whatsapp.net',
        'Rafael Alves',
        'As frutas dessa semana estão muito boas, especialmente as maçãs. Comprei 3 kg!',
        NOW() - INTERVAL '11 hours',
        'Hortifrúti',
        'Hortifrúti',
        'Positivo',
        'Positivo',
        'Filial Centro',
        'aberto'
    ),
    (
        '5544999110023@s.whatsapp.net',
        'Beatriz Nunes',
        'O banheiro feminino está sem papel e sem sabonete. Já é a segunda vez nesta semana.',
        NOW() - INTERVAL '4 hours',
        'Limpeza',
        'Geral',
        'Urgente',
        'Negativo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110024@s.whatsapp.net',
        'Gustavo Lima',
        'Excelente atendimento do repositor do corredor de bebidas. Me ajudou a encontrar tudo que eu precisava e deu dicas de promoção.',
        NOW() - INTERVAL '15 hours',
        'Atendimento',
        'Bebidas',
        'Positivo',
        'Positivo',
        'Matriz',
        'aberto'
    ),
    (
        '5544999110025@s.whatsapp.net',
        'Cristina Vieira',
        'A falta de carrinhos é constante. Cheguei hoje e não tinha nenhum disponível na entrada. Tive que esperar 10 minutos.',
        NOW() - INTERVAL '6 hours',
        'Geral',
        'Entrada',
        'Urgente',
        'Negativo',
        'Matriz',
        'aberto'
    );
-- ======================================
-- PRONTO! Dados de demonstração carregados.
-- Atacaforte | Aberto das 08:00 às 19:30
-- ======================================