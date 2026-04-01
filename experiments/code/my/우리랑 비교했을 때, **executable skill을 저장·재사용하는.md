우리랑 비교했을 때, **executable skill을 저장·재사용하는 계열**의 핵심 한계는 대체로 다음처럼 정리할 수 있어.

## 1. 재사용 단위가 너무 coarse하다

이들은 보통 “이 task에서 유용했던 procedure”를 skill로 저장하고, 다음 task에서 다시 꺼내 쓰는 식이야.
즉 중심이 **inter-task reuse**다.

하지만 실제 long-horizon execution에서는 task 전체보다 더 자주 반복되는 건:

* recipient resolve
* prerequisite check
* entity grounding
* intermediate value propagation
* failure recovery

같은 **local context pattern**이야.

우리 쪽은 이 local context를 실행 중에 분리해서 해결하고 재사용하려고 하는 반면, 기존 executable skill 계열은 보통 “task-level routine” 중심이라 **inter-context reuse**를 충분히 활용하지 못한다.

---

## 2. 실행 중 새롭게 드러난 subproblem에 늦다

기존 executable skill reuse는 대체로

* 미리 저장해둔 skill을 retrieval하거나
* 오프라인 로그에서 반복 패턴을 추출하거나
* scenario/task chain에서 skill을 학습

하는 방식이 많아.

즉 **이미 본 적 있는 패턴을 다시 쓰는 데는 강하지만**,
현재 실행 중 처음 드러난 dependency를 **그 자리에서 새 local context로 분리해 해결**하는 능력은 약하다.

우리 방법은 오히려 이 지점에 초점이 있다:

* execution이 unresolved need를 드러내면
* 그걸 helper/subprocedure로 승격하고
* 그 자리에서 recursive하게 solve한다.

즉 기존은 **reuse-first**, 우리는 **isolate-and-solve-first**에 가깝다.

---

## 3. retrieval된 skill이 현재 문맥에 정확히 맞는다는 보장이 약하다

실행 가능한 skill이라 해도, 실제로는 여전히:

* 현재 task의 제약
* 현재 environment state
* 지금까지의 intermediate results

와 정확히 맞아야 한다.

그런데 기존 방식은 대개 skill retrieval 후 그대로 쓰거나 약간 조정하는 식이라,
**현재 uncovered context에 딱 맞는 국소적 수정**이 필요할 때는 부정합이 생기기 쉽다.

우리 방법은 애초에 skill을 “retrieve해서 맞춰 쓰는 것”보다,
**현재 context 안에서 필요한 procedure를 다시 grounding하고 수정**하는 방향이라 더 직접적이다.

---

## 4. monolithic execution을 근본적으로 깨지 못한다

skill이 있어도 많은 기존 방식은 여전히 상위 agent가 하나의 큰 trajectory 안에서:

* 어떤 skill을 쓸지 고르고
* 그 결과를 이어 붙이며
* 긴 history 위에서 계속 reasoning

한다.

즉 skill reuse가 있어도 **execution context 자체는 여전히 monolithic**인 경우가 많다.

반면 우리는 새로운 국소 문제가 나오면 아예 **그 문제를 별도 local context로 isolate**한다.
그래서 skill reuse 이전에 먼저 **context disentanglement**가 일어난다.

---

## 5. skill 생성/재사용이 benchmark 구조나 retrieval 조건에 묶이기 쉽다

기존 executable skill 계열은 종종:

* similar task chain
* same scenario
* query overlap
* frequent subsequence
* pre-defined merge boundary

같은 비교적 favorable한 구조에 의존해.

즉 skill reuse가 잘 되는 이유가
“정말 일반적인 reusable subroutine이라서”라기보다,
**task grouping이나 retrieval condition이 이미 reuse에 유리하게 설계되어 있어서**일 수 있다.

우리 framing은 이런 사전 grouping보다,
**실행 중 실제로 필요가 드러난 순간의 local context**를 기준으로 모듈화를 한다는 점이 더 강하다.

---

## 6. 저장된 것은 executable이어도, 수정은 여전히 coarse하다

기존 방식은 executable skill을 저장할 수는 있어도,
그 skill이 현재 상황에서 조금 어긋나면 보통:

* 다른 skill을 찾거나
* 상위 reasoning으로 우회하거나
* 새 skill을 추가 생성

하는 식이 많다.

즉 **기존 skill 내부의 국소 repair**가 주된 primitive가 아닌 경우가 많다.

우리 방법은 실행 실패가 나면 그 failing procedure를 직접 고치고,
필요하면 그 안에서 더 작은 helper를 분리한다.
즉 저장과 재사용뿐 아니라 **repairability**가 핵심이다.

