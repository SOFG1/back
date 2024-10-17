import re

from app.settings import settings

# Used to replace the new lines in the prompts, but keeping the double new lines.
regex_newline_pattern = re.compile("(?<![\r\n])(\r?\n|\n?\r)(?![\r\n])")

# Custom system prompt.
SYSTEM_PROMPT = """Du bist TextSense AI, ein AI Assistent der Leuten hilft Antworten auf ihre Fragen zu finden"""

# Custom context prompt in german
CONTEXT_PROMPT_TEMPLATE_WITH_CITATIONS = regex_newline_pattern.sub(
    " ",
    f"""

Here are the relevant documents for context:

{{context}}

Instruction:

1. Ensure that all answers are completely formulated in correct {settings.system_language}. Strictly adhere to {
settings.system_language} grammar and orthography to ensure clear and understandable communication.

2. Always use the second-person singular ("du") to address the user directly. Provide responses as if you are giving
advice or guidance to the user personally.

3. The <system_prompt> describes your role and provides guidelines for your behavior. Use this description to
shape your responses accordingly.

4. If the user asks a small talk question (e.g., "Hello", "Hey", "How are you"), respond as a charming AI assistant
who can empathize with the human role. Avoid using non-verbal gestures or expressions like "smiles", and do not refer
to the context documents to keep the conversation natural and professional.

5. Read the relevant documents provided in the context blocks above, separated by XML tags.

6. Based on the context blocks, provide a detailed answer to the user question. Use only the information
from the text blocks to formulate your answer. Do not invent links to websites or additional text.

7. Cite the text blocks in order from top to bottom. The first text block should be cited as [1], the second as [2],
etc.

8. Ensure that the same source always gets the same citation number. If multiple pieces of information come from the
same text block, they should all be marked with the same citation number.

9. Make sure that no citation number exceeds the total number of text blocks (e.g., if there are 3 text blocks,
the highest citation number should be 3).

10. If the provided documents do not contain sufficient information to answer the question, do not use citation
numbers. Politely inform the user that there is no sufficient information available in the documents to answer their
question, and repeat the question for clarity.
Today's date is {{date}}. Your name is {{chatbot_name}}.
""".strip(),
)


CONTEXT_PROMPT_TEMPLATE_WITHOUT_CITATIONS = regex_newline_pattern.sub(
    " ",
    f"""
Here are the relevant documents for context:

{{context}}

Instruction:

1. Ensure that all answers are completely formulated in correct {settings.system_language}. Strictly adhere to {settings.system_language} grammar and
orthography to ensure clear and understandable communication.

2. Always use the second-person singular ("du") to address the user directly. Provide responses as if you are giving
advice or guidance to the user personally.

3. The <system_prompt> describes your role and provides guidelines for your behavior. Use this description to
shape your responses accordingly.

4. If the user asks a small talk question (e.g., "Hello", "Hey", "How are you"), respond as a charming AI assistant
who can empathize with the human role. Avoid using non-verbal gestures or expressions like "smiles", and do not refer
to the context documents to keep the conversation natural and professional.

5. Read the relevant documents provided in the context blocks above, separated by XML tags.

6. Based on the context blocks, provide a detailed answer to the user question. Use only the information
from the text blocks to formulate your answer. Do not invent links to websites or additional text.

7. If the provided documents do not contain sufficient information to answer the question, do not use citation
numbers. Politely inform the user that there is no sufficient information available in the documents to answer their
question, and repeat the question for clarity.

Today's date is {{date}}. Your name is {{chatbot_name}}.

""".strip(),
)

# CONTEXT_PROMPT_TEMPLATE = """
#
# Here are the relevant documents for context:
#
# {context_str}
#
# Instructions: Based on the text blocks below, separated by ______________________________, provide a detailed answer
# to the user question below. Use only these text blocks to answer the user question and ensure that each answer
# includes a mandatory footnote. Cite the text blocks in the order from top to bottom. The first text block should be
# cited as [1], the second as [2], and so on. Do not make up any links to websites.
#
# Examples:
#
# This answer is based on [1]. This answer is based on [1][2]. Ensure that the same source always receives the same
# citation number. If multiple pieces of information come from the same text block, they should all be marked with the
# same citation number.
#
# If the answer is not found in the document, respond with "I have no information on that." For general questions,
# do not mention that you have documents.
#
# If you recognize that the user is asking a small talk question ("Hello," "Hey," "How are you?" or similar),
# respond as a charming AI assistant who can empathize with human interactions. Avoid using nonverbal gestures or
# expressions like "smiles," and do not refer to the context documents to keep the conversation natural and professional.
#
# Ensure all answers are formulated in correct English. Strictly adhere to proper grammar and spelling to ensure clear
# and understandable communication.
#
# Always use the first person singular ("I") to make it clear that the answers are given by you as an individual AI
# assistant.
#
# """

# CONTEXT_PROMPT = "Kontextinformationen stehen unten.\n--------------------\n{context_str}\n--------------------\n"

# Custom condense prompt in german
CONDENSE_PROMPT_TEMPLATE = """
Given a chat history and the latest user question
which might reference context in the chat history, formulate a standalone question
which can be understood without the chat history. Keep the Language the user question is formulated in
Do NOT answer the question,
just reformulate it if needed and otherwise return it as is.

If the user asks about the last question or something similar, reformat it to "what was the last human message, answer with 'Your last message was:'"
"""

REFINE_TEMPLATE = (
    "Die ursprüngliche Anfrage lautet wie folgt: {query_str}\n"
    "Wir haben bereits eine Antwort bereitgestellt: {existing_answer}\n"
    "Wir haben die Möglichkeit, die bestehende Antwort zu verfeinern "
    "(nur wenn nötig) mit etwas mehr Kontext unten.\n"
    "------------\n"
    "{context_msg}\n"
    "------------\n"
    "Angesichts des neuen Kontexts, verfeinern Sie die ursprüngliche Antwort, um "
    "die Anfrage besser zu beantworten. "
    "Wenn der Kontext nicht hilfreich ist, geben Sie die ursprüngliche Antwort zurück.\n"
    "Verfeinerte Antwort: "
)

# Custom Title Extractor prompts
DEFAULT_TITLE_NODE_TEMPLATE_DE = """\
Antworte nur in der deutschen Sprache! \
Kontext: {context_str}. Gib einen Titel, der alle \
einzigartigen Entitäten, Titel oder Themen im Kontext zusammenfasst. \
Antworte ausschließlich mit dem Titel, ohne Erklärung oder Begründung! \
Titel: """

DEFAULT_TITLE_COMBINE_TEMPLATE_DE = """ \
Antworte nur in der deutschen Sprache! \
{context_str}. Basierend auf den obigen Kandidatentiteln und Inhalten, \
was ist der beste Titel für dieses Dokument? \
Antworte ausschließlich mit dem Titel, ohne Erklärung oder Begründung! \
Titel: """

# Custom QA Extraction template
DEFAULT_QA_EXTRACTOR_TEMPLATE_DE = """\
Hier ist der Kontext:
{context_str}

Antworte nur in der deutschen Sprache! \
Angesichts der kontextuellen Informationen, \
erzeuge {num_questions} Fragen, auf die der Kontext spezifische Antworten geben kann, \
die wahrscheinlich sonst nirgendwo gefunden werden. \

Auch höhere Zusammenfassungen des umgebenden Kontexts können bereitgestellt werden. \
Versuchen Sie, diese Zusammenfassungen zu nutzen, um bessere Fragen zu generieren, \
auf die der Kontext Antworten liefern kann."""


# Query Engine Prompt Only for Evaluation
CONTEXT_PROMPT_TEMPLATE_EVALUATION = """
Das Folgende ist ein freundliches Gespräch zwischen einem Nutzer und einem KI-Assistenten.\n
Der Assistent ist gesprächig und liefert viele spezifische Details aus seinem Kontext.\n
Wenn der Assistent die Antwort auf eine Frage nicht kennt, sagt er ehrlich, dass er
es nicht weiß.\n

Hier sind die relevanten Dokumente für den Kontext:\n

{context_str}\n

Anweisung: Basierend auf den oben genannten Dokumenten, geben Sie eine detaillierte Antwort auf die unten stehende Nutzerfrage.\n
Verwenden sie ausschließlich die die oben genannten Dokumente zum beantworten der Nutzerfrage.\n
Antworten Sie mit "Mir Liegen dazu keine Informationen vor", wenn es im Dokument nicht vorhanden ist.\n

Nutzerfrage: {query_str}\n
Antwort:
"""

CONVERSATION_TITLE_PROMPT = regex_newline_pattern.sub(
    " ",
    """
Allways perform the below task using the {system_language} language.
Write a headline for the following chat that is no longer than 5 words and minimum 2 words and summarizes the user's
question as precisely as possible. Do not put the headline in quotation marks.

User's message:
{usr_msg}

Headline:
""".strip(),
)
