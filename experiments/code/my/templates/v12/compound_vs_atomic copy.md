USER:
R1, R2, and R3를 명심한 채로 my problem을 해결할 것이다.
그 전에, 너에게 규칙을 설명해주겠다.

여러 함수들을 도입하고 이들을 잘 엮어서 내 문제를 해결할 거야.
함수는 실행 과정에서 필요할 때 just-in-time 구현한다.

# PLANNING-FRST VS. EXPLORATION-FRST
너는 둘 중 하나의 모드를 이용해서 각 함수의 expected functionality를 만족하는 구현을 완성할 것이다.
첫 번째 모드는 planning-first, 다른 모드는 exploration-first야.
불확실성이 존재하거든.

# WHEN TO PLAN AND WHEN TO EXPLORE
1. planning-first. 태스크 해결의 구조/control flow가(구현 디테일이 아닌 '구조') '명확'할 때. 즉, 주어진 정보에만 근거해서 판단했을 때, 태스크 해결 구조가 훤히 보이고, 각 부분 문제들이 해결 가능하다는 것이 명확할 때. 추가 관측이 들어와도 전체 흐름은 유지되고 세부만 바뀌면 계획 가능하다. 구체적인 구현보다는 바뀔 가능성이 없는 견고한 뼈대를 세우는 데 집중한다.
2. exploration-first. 태스크 flow 구조 자체가가 불명확할 때. 즉, 쪼갠 하위 문제를 실제 도구와 관측으로 풀 수 있는지 불명확할 때.

# ...
각 해결 모드에 따라 너의 행동은 다음과 같다.
1. planning-first. Write a high-level orchestration skeleton for the target function without any 불확실성 and with full robustness to any unknown details.
2. exploration-first. Write what you want to explore in text. We will proceed in repeated exploration rounds. Each round is for exploring one specific thing, not multiple.

## PLANNING-FIRST DISCIPLINE
Explected functionality를 보고 "견고한" control flow 뼈대를 만든다.
When needed, use standard control flow statements (e.g., if/else, loops).
1. 해결 가능함이 보장된 하위 문제들을 분석한다.
2. Name the helper functions for each subtask. Helper function names must describe what must be done (the intent), not how it is done.
3. Call the helper functions to orchestrate the execution flow.

Make data flow across helper functions visible.
1. Assign the return value of every helper function call to a new local variable.
2. Pass these new local variables as arguments to subsequent helper calls to show explicit data dependency. If a call is a "sink call" (no subsequent calls need its return value), you must still assign its return value to a local variable, and simply pass it to `print`. 

Focus on 견고한 뼈대.
1. Every call must be a helper function call. Do NOT implement.
2. NEVER access inner fields or properties of a return value. You do NOT know yet what a helper function would return.
3. Pass the whole/rich object. Even if a subsequent step only needs a specific piece of data, pass the richest context to the helper function to give the future implementation total freedom.

## EXPLORATION-FIRST DISCIPLINE

# RESPONSE FORMAT
```
{
  "reason": "<brief explanation>",
  "type": "compound|atomic"
}
```

Write a high-level orchestration skeleton for the target function.  
Do not include uncertain assumptions or fragile implementation details.  
The goal is to produce a robust task-solving skeleton that remains valid despite unknown details.

2. exploration-first. Write what you want to explore in text. We will proceed in repeated exploration rounds. Each round is for exploring one specific thing, not multiple.


```python
{{ snapshot.fn.dumps(with_docstring=False, ctx=snapshot.ctx, print_locals=True) }}
```

# COMPOUND VS ATOMIC
- Classify as `atomic` if the core task is naturally completed by exactly one central, primary API call as the final task-completing step (the sink), with no API calls needed afterward. Branching, looping, or other processing is allowed after the sink if it does not involve additional API calls.
- Classify as `compound` otherwise.

# EXPECTED FUNCTIONALITY
{{ snapshot.fn.doc(fmt="markdown") }}

{% if include_response_format | default(true) -%}
# RESPONSE FORMAT
```
{
  "reason": "<brief explanation>",
  "type": "compound|atomic"
}
```

{% endif -%}