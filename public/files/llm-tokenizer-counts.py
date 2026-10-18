import tiktoken
en="A language model reads text as a sequence of tokens, not letters or words. Each token is an integer, and the model predicts the next integer one step at a time."
ko="언어 모델은 글자나 단어가 아니라 토큰의 나열로 텍스트를 읽는다. 각 토큰은 정수이고, 모델은 다음 정수를 한 번에 하나씩 예측한다."
code="def add(a, b):\n    return a + b\n\nprint(add(2, 3))\n"
num="3141592653589793238462643383279502884197"
for name in ['gpt2','cl100k_base','o200k_base']:
    e=tiktoken.get_encoding(name)
    print(name, 'vocab',e.n_vocab)
    for lab,t in [('en',en),('ko',ko),('code',code),('digits',num)]:
        print(' ',lab,len(t),'chars',len(e.encode(t)),'tokens')
e=tiktoken.get_encoding('cl100k_base')
for w in ['tokenization',' tokenization','Tokenization','unbelievably','strawberry','안녕하세요','토큰화','1234567']:
    print(repr(w),[e.decode([i]) for i in e.encode(w)])
