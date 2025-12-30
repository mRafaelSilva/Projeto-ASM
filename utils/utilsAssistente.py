import re

def get_intencao(texto):
	texto = texto.lower()
	# Foca apenas em palavras-chave óbvias para a intenção
	padroes = {
		'inscricao': r'(inscre|matricu|inscri)',
		'equivalencia': r'(equivalen|aproveita|creditar)'
	}
	for intencao, padrao in padroes.items():
		if re.search(padrao, texto):
			return intencao
	return None

def extrair_slots(intencao, texto):
	slots = {}
	texto = texto.lower().strip()

	if intencao == "inscricao":
		# 1. CURSO: Captura siglas ou nomes após "em", "no" ou "curso"
		m_curso = re.search(r'(?:curso de|curso|em|no)\s+([a-z]{2,4}\b|[^,.\n\s]+)', texto)
		if m_curso:
			slots['curso'] = m_curso.group(1).strip()

		# 2. NÚMERO: Qualquer sequência numérica após rótulos comuns
		m_num = re.search(r'(?:n[úu]mero|aluno|id|n[ºo])[\s:]*(\d+)', texto)
		if m_num:
			slots['numero_aluno'] = m_num.group(1)

		# 3. DISCIPLINA: Captura após "disciplina" ou "cadeira"
		# Se o texto capturado contiver o curso, ele é removido
		m_disc = re.search(r'(?:disciplina|cadeira|unidade)(?: de| em)?\s+([^,.\n]+)', texto)
		if m_disc:
			res = m_disc.group(1).strip()
			
			# Limpeza dinâmica: Se o curso já foi detetado, removemos do nome da disciplina
			if 'curso' in slots:
				# Remove " de curso" ou " em curso" ou apenas "curso" no final da frase
				res = re.sub(rf'\s+(?:de|em|no|na)?\s*{re.escape(slots["curso"])}\b', '', res).strip()
			
			# Só guarda se o resultado não for o próprio curso
			if res and res != slots.get('curso'):
				slots['disciplina'] = [res]
            
	return slots