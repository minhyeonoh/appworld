
# LOOP https://arxiv.org/pdf/2502.01600
Qwen2.5-32B-Instruct + RL

- 71.3% on normal
- 53.6% on normal all-pass@3
- 45.7% on challenge
- 26.6% on challenge all-pass@3

## 어던 문제를 풀었는가?

* 같은 task에 대해 여러 rollout을 샘플링하고
* 각 rollout의 reward를 **통과한 unit test 비율**로 계산한 뒤
* 그 reward들로 **leave-one-out advantage**를 만들고

  * 즉, **내 reward − 나를 제외한 같은 task의 다른 rollout들 평균 reward**
  * 해석하면, **같은 문제 안에서 남들보다 얼마나 잘했는가**
* 그 advantage를 써서 **PPO 업데이트**를 한다.

**LOOP는 같은 task에 대한 여러 rollout의 상대적 성공도(LOO advantage)를 unit-test 기반 reward로 계산하고, 이를 이용해 PPO로 policy를 학습한다.**

## 저자들이 관찰한 것

* RL 이후 에이전트가 **AppWorld에서 필요한 행동 습관**을 더 잘 보인다.
* 구체적으로,

  * API 문서를 더 자주 읽고
  * 불필요한 가정을 덜 하고
  * placeholder/dummy 값을 덜 쓰고
  * API 에러 뒤에 덜 포기하고,
  * 실행 결과를 보기 전에 여러 단계를 한꺼번에 배치하는 행동도 줄어든다.

* `show_api_doc` 호출 약 **1.6배 증가**
* “assuming”류 표현 약 **30배 감소**
* “dummy” 약 **6배 감소**
* 실패 후 포기 약 **3배 감소**
* multiple code cells per turn도 약 **6배 감소**

## 중요한 해석 포인트

* 이 현상들은 **학습 목표에 직접 넣은 규칙이 아니다.**
* 즉, 학습이
  “문서를 읽어라”
  “포기하지 마라”
  “가정하지 마라”
  “한 번에 여러 단계를 몰아서 실행하지 마라(실행 결과 보고 다음 행동 진행해라)”
  를 **직접 강제한 것은 아니다.**
* 그냥 **task reward만으로 학습했는데**, 결과적으로 이런 행동 경향이 나타난 것이다.

그래서 네 Note가 중요해:

* **이건 사후 관찰된 behavioral change이지, 직접적 supervision의 결과는 아니다.**

## 왜 AppWorld에서 이런 변화가 중요하다고 해석하나

* AppWorld는 API 함수가 많고, 파라미터도 많아서 **추측으로 밀어붙이기 어려운 환경**이다.
* 저자들은 AppWorld에 **457개 API 함수**와 **1470개 함수 파라미터**가 있어 문서 조회가 중요하다고 설명한다.
* 또 초반의 잘못된 가정은 뒤에서 **downstream error로 길게 전파**될 수 있다고 본다.
* 마찬가지로, 중간 실행 결과를 확인하지 않은 채 여러 code cell을 한 번에 배치하는 open-loop식 행동은 stateful 환경에서 특히 불리하다. 앞 단계가 예상과 다르면 뒤 단계 전체가 연쇄적으로 틀릴 수 있기 때문이다. 그래서 multiple code cells per turn 감소는, RL이 에이전트를 더 신중한 closed-loop / interactive policy 쪽으로 밀어주었다는 신호로 해석할 수 있다.

그래서 이 환경에서는

* 정답 문장을 그럴듯하게 생성하는 능력보다
* **필요한 정보를 충분히 조회하고**
* **성급한 가정을 피하고**
* **중간 실패를 복구하는고**
* 중간 관찰을 보며 단계적으로 행동을 조정하는 sequential behavior

가 더 중요하고, 저자들은 RL이 바로 그쪽을 밀어줬다고 해석한다.

## 한계

LOOP의 학습 성공은 AppWorld가 제공하는 잘 설계된 unit tests에 크게 의존.
저자들은 reward를 그냥 통과한 unit test 비율로 둠.
좋은 reward가 이미 있는 환경에서 RL을 검증.
In practice, user feedback is sparse. 이 경우에는 성공률이 확연히 떨어질 것(가설).

학습 신호가 최종 outcome 쪽에 치우쳐 있어 credit assignment가 거칠다. 어떤 중간 행동이 좋았는지 직접 구분하지 않고, 최종 성공/실패를 rollout 전체에 거의 통째로 귀속한다. 저자들이 behavioral change를 관찰하긴 했지만, 알고리즘 자체는 “문서 조회”, “가정 회피”, “복구” 같은 중간 행동에 대한 별도 shaping을 쓰지 않는다. 그래서 긴 horizon에서 어느 스텝이 실제로 기여했는지 세밀하게 가르치지는 못한다는 한계. --- 개념적으로는 한계이지만, 실증적으로는 생각만큼 치명적이지 않았던 것 같음. 높은 성능을 보고했고, behavioral analysis에서도 문서 조회 증가, assumption 감소, open-loop batching 감소 같은 바람직한 변화가 나타남.

# Strategy-Guided Exploration (SGE) https://arxiv.org/pdf/2603.02045
Qwen3-8B-Think + RL
- 66.6% on normal (easy)

## 어떤 문제를 풀었는가?
LLM agent RL의 병목은 exploration. sparse reward 환경에서 보통 RL은 기존 base model이 이미 가끔 내던 답 주변만 더 다듬는 경향이 있고, 정말 새로운 성공 trajectory를 찾는 데는 약하다는 것. 특히 agent는 action space가 코드, tool call, UI action처럼 언어적이고 길어서, 그냥 temperature를 올려 low-level action을 흔드는 방식은 “겉보기로만 다른 행동”을 많이 만들 수 있다.

## 핵심 아이디어
먼저 고수준 자연어 strategy를 다양하게 탐색하게 하자. “지금 무엇을 해서 진전할지”를 설명하는 짧은 strategy 문장을 생성한 뒤, 그 strategy에 조건부로 action을 생성한다. 즉 exploration의 공간을 action space에서 strategy space로 올려버리는 거야. 저자 주장에 따르면, 이렇게 하면 서로 다른 environment outcome으로 이어질 가능성이 높은, 구조적이고 의미 있는 탐색이 쉬워진다.

1. “전략은 다양하게, 실행은 안정적으로” (mixed-temperature sampling). strategy 토큰은 더 높은 temperature로 샘플링하고, 그 뒤의 action 토큰은 더 낮은 temperature로 샘플링한다.
2. strategy reflection. 이전에 실패한 strategy를 보여주고 “왜 실패했는지 비판하고 다른 strategy를 내라”는 식으로 다음 strategy 생성을 유도한다. 성공한 strategy를 참고하는 positive reflection도 일부 쓰지만, 논문에서는 실패 strategy 기반 reflection이 더 중요했다고 말한다.

## 한계
AppWorld에서 SGE가 진짜로 base model의 능력 경계를 넓혔다기보다, 이미 잠재적으로 가능하던 행동을 일부 잘 끌어내는 효과일 수 있음. SGE의 pass@1은 Base model의 pass@8 정도. pass@k의 upper bound (up to where the pass@k does not change when doubling k)를 넘지 못함. Gap은 대략 10%p 정도. 실용적으로는 여전히 좋은 결과이지만, 여전히 improvement room이 존재.

# Skill Augmented GRPO for self-Evolution (SAGE) https://arxiv.org/pdf/2512.17102
Qwen2.5-32B Instruct + RL

- 72.0% on normal
- 60.7% on normal all-pass@3
- 50.1% on challenge
- 32.4% on challenge all-pass@3

## 어떤 문제를 풀었는가?
기존의 skill-library 에이전트는 대체로 prompt engineering에 많이 의존하고, 일반적인 RL도 보통 현재 task의 outcome reward만 최적화합니다. 그래서 “이 skill이 다음 유사 task에서 실제로 재사용될 만큼 좋은가?”를 직접 학습시키기 어렵습니다. 그러면 일관된 skill generation / utilization이 어렵다.

## 핵심 아이디어
보너스 리워드
- “이 스킬을 만들어 둔 것이 이후 task에 정말 도움이 되었는가?”
- “이전에 만들어 둔 스킬을 사용했는가?”

첫 task reward = 첫 task 성공 + 둘째 task도 성공 + 둘째 task가 첫 task의 skill을 실제 사용
둘째 task reward = 둘째 task 성공 + skill 사용

## 한계

1. Strong expert dependence. 저자들은 Claude 3.5 Sonnet V2를 expert로 써서 SFT를 먼저 수행합니다. 또 expert dataset도 그냥 수집한 게 아니라 rejection sampling을 돌리고, 첫 두 개 혹은 세 개 task가 성공한 scenario만 남겨서 최종 1,129개 valid example을 만듭니다. 즉 초기화가 상당히 강하게 정제되어 있습니다. 이미 잘 정제된 expert behavior를 먼저 모방한 뒤 개선한 구조다.

2. skill library의 기여는 general task competence를 크게 바꾼다기보다 scenario transfer metric에서 더 크게 나타난다. 따라서 “skill learning이 실제 문제 해결 능력을 본질적으로 높였다”기보다는, 재사용 행동을 강화한 것에 가까움.

SAGE
- 72.0% on normal
- 60.7% on normal all-pass@3
SAGE w/o skill library
- 71.4% on normal
- 54.8% on normal all-pass@3
LOOP 
- 71.3% on normal
- 53.6% on normal all-pass@3

3. Training requires "pre-defined" task chains of similar tasks. 현실적으로, 유사 task가 연속으로 neatly 주어지지 않을 수 있고 task ordering이 불안정하며 어떤 task들이 같은 chain에 속하는지 미리 아는 것도 어렵고 reward를 chain 단위로 연결하기도 어렵다는 점입니다. SAGE의 핵심인 Sequential Rollout은 single task가 아니라 similar task chain을 필요로 합니다. 논문도 아예 chains of similar tasks를 샘플링한다고 설명하고, 보상도 “앞 task가 만든 skill이 뒤 task에서 성공적으로 쓰였는가”에 달려 있습니다.

4-1. idealized evaluation setting. "skills are retained and utilized only within the same scenario." 실제 환경에서는 scenario boundary가 명확하지 않을 수 있고 “같은 scenario 안에서만 memory를 유지”하는 설정은 retrieval를 너무 쉽게 만든다.
4-2. Query N-gram being almost as good as Same Scenario is suspiciously favorable. 보다 일반적인 retrieval 방식의 실험에서 비슷한 성능을 내지만, AppWorld 내 same-scenario tasks의 쿼리가 자연어적으로 매우 비슷하기 때문에, 단순 n-gram 겹침만으로도 사실상 ideal한 same scenario setting처럼 작동하는 것이 당연함.

Although the paper formulates skills as reusable programmatic functions, in practice their creation, indexing, and retrieval appear tightly coupled to individual queries/scenarios, making the learned “skills” closer to task-conditioned function memories than truly fine-grained, task-agnostic subroutines.

# Acon (Agent Context Optimization) https://arxiv.org/pdf/2510.00615
ReAct (GPT 4.1) + Context Compression (GPT 4.1)

- 56.5% on normal

## 어떤 문제를 풀었는가?
장기 horizon LLM agent (ReAct)에서 계속 길어지는 context를 어떻게 줄일 것인가? step이 진행될수록 action/observation/thought가 계속 누적되어 입력 토큰이 끝없이 커집니다. 그러면 비용이 커질 뿐 아니라, 오래된 잡정보가 섞여서 오히려 agent 판단이 흐려질 수 있습니다. FIFO truncation은 불충분. compression seems good, but limited:
- 간결성 편향 (Brevity Bias): 기존의 프롬프트 최적화 방법론(예: GEPA)들이 '짧고 간결한 지시사항'을 좋은 것으로 간주하고 지향. 문제 해결에 꼭 필요한 '도메인 특화 지식'이나 '세부적인 예외 처리 규칙' 등을 누락시키는 경우가 많습니다.
- 컨텍스트 붕괴 (Context Collapse): 새로운 피드백이나 교훈을 기존 컨텍스트에 반영할 때, **LLM에게 전체 문맥을 한 번에 다시 쓰도록 지시하는 방식(monolithic rewriting)**에서 발생합니다. 통째로 다시 쓰라고 하면 LLM의 특성상 이를 짧고 정보량이 적은 요약본으로 확 압축해 버리는 현상. 논문의 예시(ACE)를 보면 18,282 토큰으로 잘 유지되던 상세한 정보가 단 한 번의 업데이트 스텝 만에 122 토큰으로 날아가 버리며 성능이 급락합니다. 이는 의도한 최적화가 아니라 누적된 정보가 무너져 내리는 구조적 결함입니다.

## 헥심 아이디어
Compressor LLM이 컨텍스트가 특정 수준보다 길어질 때마다 압축. Compressor LLM의 프롬프트를 최적화. 
```
Context Window = Inst | TAOTAOTAO...TAO
Compressed Context Window = Inst | Compress(TAOTAOTAO...) | TAO
```

contrastive prompt optimization임. 
압축 전에는 성공했지만 압축 후 실패한 태스크 모음(contrastive set).
각 태스크의 성공/실패 trajectory를 보고 강한 LLM이 “무슨 정보가 빠져서 실패했는지”를 분석(필수 정보 식별).
이렇게 모은 피드백들 바탕으로, 압축 가이드라인 프롬프를 업데이트.
"if the agent fails with compressed context while succeeding without compression, this indicates that the compressed context may have lost crucial information."

두 단계 최적화:
1. UT (utility maximization) -> P1. “압축 가이드라인 업데이트 후보들 중 가장 좋은 것으로” Constrastive set에서 재평가 후 best 고름.
2. CO (compression maximization) -> P2. “더 짧게” 압축 후 성공했던 태스크 trajectory들을 보고 어떤 정보가 유용했는지 평가. 해당 평가들을 보고 P1을 간결화.

## 한계

1. 최적화 자체의 메타 비용이 있음 (배포 전): guideline prompt를 만들기 위해 full/compressed trajectory를 여러 개 수집하고, 강한 LLM으로 실패 원인을 분석하고, 후보 prompt들을 반복 평가해야 한다. 따라서 새 도메인마다 별도의 upfront cost가 발생한다.
2. 배포 후에도 추가 실행 비용이 듦. compressor를 계속 호출해야 하므로, 태스크 해결 자체를 위한 비용 외에 추가 API 비용이 발생할 수 있다. 특히 history compression은 실제 총 비용이나 latency를 줄이지 못할 가능성이 있다.
3. 강한 optimizer LLM 의존성이 있음(textgrad). 좋은 guideline을 얻으려면 o3 같은 강한 optimizer model이 필요해 보인다. 즉, 방법의 품질이 optimizer의 추론 능력에 상당히 의존할 수 있다.
4. 전체 history compression의 필요성이 불분명. 매 step에서 정말로 이전 히스토리 전체를 요약한 압축 정보를 context로 가지고 다녀야하는지 불분명. 많은 경우 현재 step(또는 segment)에 필요한 것은 과거 전체의 압축본이라기보다, 일부 핵심 상태나 최근 몇 개의 관련 정보임. 압축도 압축이지만, 각 step이나 segment의 실행 맥락에 따라 history를 분리(credit assignment?)하는 게 우선이라는 생각.
5. 과거 히스토리에는 당장 다음 step에는 필요없던 정보이더라도 근(먼)미래의 step에서는 필요한 정보가 있을 수 있음. 하지만, ACON은 이러한 정보를 날려버릴 수 있음.

# PAACE (Plan-Aware Automated Context Engineering) https://arxiv.org/pdf/2512.16970
ReAct (GPT 4.1) + Context Reshape (GPT-OSS-120B)

- 59.0% on normal

## 어떤 문제를 푸는가?

과거 히스토리만 보고 context를 compression하는 것은 위험함. 과거 히스토리에는 당장 다음 step에는 필요없던 정보이더라도 근(먼)미래의 step에서는 필요한 정보가 있을 수 있음(precondition, intermediate state, temporal dependency). 그래서 지금 당장 안 쓰여도 2~3 step 뒤에 필요한 정보를 미리 보존해야 한다는 게 핵심 문제의식입니다.

## 핵심 아이디어
"plan-conditioned reshaping"
```
Context Window = Inst | TAOTAOTAO...TAO | subtasks (plan)
Compressed Context Window = Reshape(Inst | TAOTAOTAO..., "next k subtasks") | TAO | "next k subtasks"
```

## 한계

benchmark가 제공하는 구조화된 정답형 계획 분해를 그대로 사용(매우 크리티컬) "Plan descriptions Π are obtained either directly from benchmarks that provide structured task decompositions (e.g., AppWorld, OfficeBench), or from..."

# Agent Workflow Optimization (AWO) https://arxiv.org/pdf/2601.22037
ReAct (GPT 5.1) + 여러 api 호출 시퀀스를 하나의 meta-tool로 만들어서 저장/활용

Note: on normal
- GPT 5.1: 69.6%
- GPT 5.1 + AWO: 73.2%
- Claude 4.5: 89.3%
- Claude 4.5 + AWO: 85.7%
- GPT-OSS 120B: 14.3%
- GPT-OSS 120B + AWO: 16.1%

## 어떤 문제를 풀었는가?
ReAct류 agent는 유연하지만, 매 단계마다 "생각 → 도구 호출 → 관찰 → 다시 생각"을 반복해서 LLM 호출 수, 비용, 지연, 실패 기회가 계속 늘어납니다. 서로 다른 task라도 초반부에 비슷한 tool-call prefix를 자주 공유한다고 봅니다. 즉 agent가 매번 같은 루틴을 새로 “생각”하고 있다는 거예요.

## 핵심 아이디어
실행 로그(오프라인)에서 자주 반복되는 도구 호출 시퀀스를 찾아서, 그 시퀀스를 하나의 결정적 composite tool, 즉 meta-tool로 컴파일한다. 그러면 agent는 그 구간에서 중간 reasoning을 여러 번 할 필요 없이, meta-tool 한 번 호출로 넘어갈 수 있습니다. -> 반복 reasoning 구간을 tool abstraction으로 제거해서 step 수를 줄임

1. 실행 로그 사전 수집
2. 로그들에서 semantically equivalent한 툴 호출 subsequence 식별
3. 툴 호출 subsequence들을 노드로, 엣지는 한 도구 호출 subsequence에서 다음 도구 호출 subsequence로 넘어가는 상태 전이. 실행 로그 상 두 subsequence들의 전이 발견 횟수를 엣지 가중치로.
4. 연결된 노드들을 합침. 자식 노드가 여러 개일 경우(합친 노드들이 자식 개수만큼 생길 것임), 합치고 난 그래프 가중치 합이 감소할 때만 합침. 

## 한계

1. 실행 로그 사전 수집 필요, source 불분명.
2. 일반화(Generalization) 검증 부족: 최종 토큰 사용량과 비용 절감 효과를 평가할 때도 동일한 168개 태스크를 그대로 사용했어. 즉, 평가용 정답지(Test 셋)를 미리 보고 맞춤형 최적화 도구를 만든 다음, 이 도구들을 이용해서 같은 정답지로 다시 시험을 친 셈이야. Train 스플릿의 로그에서 메타 도구를 추출하고, Test 스플릿에서 그 범용적 효과를 검증했을 가능성? ㄴㄴ "test split" 키워드는 존재, but "train"이라는 단어는 남들 깔 때만 사용.
3. "determining which tool-call sequences are semantically equivalent and safe to reuse requires domain knowledge about tool behavior, side effects, and return values. As a result, it is difficult to effectively au- tomate horizontal merging and AWO relies on domain experts to specify valid merging boundaries and equivalence"
4. 사전 수집된 로그에 실패한 케이스가 있는 경우 meta tool은 어떻게 만들어져? 필터링을 해?
  - 성공 궤적만 필터링 하는 경우: 이 자체로 한계
  - 필터링 안 하는 경우: 도구 모음에 '실패로 이끄는 메타 도구'가 존재하면, 추론 능력이 약간 떨어지는 에이전트들은 이 도구가 마치 만능 키인 줄 알고 우선적으로 남용하게 되며, 결과적으로 작업 성공률(Task Success Rate)이 곤두박질치게 됩니다. "it is difficult to evaluate whether all of the rules it created were good, or whether some of them were bad enough to contaminate the whole system, making meta-tool discovery a gamble. Verification of an agent rule and meta-tool discoverer remains a future challenge."

# ACE (Agentic Context Engineering) https://openreview.net/pdf?id=eC4ygDs02R
ReAct (DeepSeek-V3.1-671B) + Evolving, context-rich, structured playbooks (전략집)
Offline
- 75.0% on normal
- 64.3% on normal all-pass@3
- 54.4% on challenge
- 35.2% on challenge all-pass@3
Online
- 69.6% on normal
- 53.6% on normal all-pass@3
- 66.0% on challenge
- 48.9% on challenge all-pass@3

ReAct (gpt-oss-120b) + Evolving, context-rich, structured playbooks (전략집)
Offline
- 58.3% on normal
- 41.1% on normal all-pass@3
- 39.6% on challenge
- 18.7% on challenge all-pass@3
Online
- 60.7% on normal
- 44.6% on normal all-pass@3
- 43.2% on challenge
- 20.1% on challenge all-pass@3

## 어떤 문제를 풀었는가?
Acon, PAACE이랑 같은 문제를 풀었음. 다만, 방향이 정반대임. '어떻게 하면 더 똑똑하게 잘 요약(압축)할 것인가'를 고민하는 대신, **"LLM에게는 요약본이 아니라 세부 정보가 모두 담긴 길고 풍부한 문맥(Context-rich)을 주는 것이 더 낫다"**며 완전히 직교하는(orthogonal) 방향을 주장. "We argue that contexts should function not as concise summaries, but as comprehensive, structured playbooks that are detailed, inclusive, and rich with domain insights."

## 핵심 아디이어
도메인 지식 측면에서 세부적(↔ 간결성 편향)이고 포괄적(↔ 컨텍스트 붕괴)인 **'구조화된 플레이북(comprehensive, structured playbooks)'**.
in both offline settings (e.g., system prompt optimization) and online settings (e.g., test-time memory adaptation).
evolving playbooks that accumulate and organize strategies over time.

- 생성기 (Generator): 주어진 쿼리와 현재의 '플레이북(컨텍스트)'을 바탕으로 문제를 풀고 실행 궤적(Trajectory)을 남깁니다.
- 반성기 (Reflector): '풍부한 교훈을 뽑아내는 것'이 목적(↔ 간결성 편향). 생성기의 실행 기록을 비판적으로 분석하여 "구체적인" 성공 요인이나 오류의 원인을 파악하고, 구체적인 교훈(Insights)을 추출합니다.
- 큐레이터 (Curator): 반성기가 찾은 교훈을 바탕으로 incremental delta updates을 만들어냄. that replace costly monolithic rewrites with localized edits. 기존처럼 프롬프트 전체를 다시 쓰는 대신(↔ 컨텍스트 붕괴), 개별 항목(Bullet points) 단위로 유용한 팁을 추가하거나 기존 항목을 수정하는 '점진적 업데이트(Incremental delta updates)' 방식을 사용합니다. 이를 통해 디테일한 정보가 붕괴하는 것을 막고, 업데이트 비용과 시간도 크게 줄입니다
- 플레이북 업데이트: deterministic.~~ 성장 및 정제 메커니즘 (Grow-and-Refine) (포괄성과 효율성의 균형). 무조건 정보를 쌓기만 하는 것이 아니라 효율적으로 관리합니다. 추가(Append): 이전에 없던 새로운 전략이나 교훈이 발견되면('의미론적 임베딩(Semantic embeddings)'을 통해 의미가 유사한지 비교) 고유한 식별자(ID)와 함께 새로운 항목(Bullet)으로 플레이북 끝에 덧붙입니다. 현행화(Update in place): 이미 존재하는 항목과 관련된 피드백이 들어오면 새로 쓰는 대신 기존 항목의 데이터를 업데이트합니다. 예를 들어, 특정 전략이 성공에 도움이 되었다면 해당 항목의 '도움됨 카운터(Counter)'를 올려서 해당 정보의 중요도나 신뢰도를 실시간으로 반영합니다.~~ 그냥 append-only 메모리임.
  <!-- - 즉각적 정제(Proactive): 매번 새로운 정보(Delta)가 추가될 때마다 즉시 중복을 제거하고 정제합니다. 컨텍스트의 정확도는 높아지지만 매번 연산이 필요하므로 지연 시간(Latency)이 늘어날 수 있습니다. 
  - 지연된 정제(Lazy): 평소에는 계속 쌓아두기만 하다가, 컨텍스트 창(Context window)이 꽉 차기 직전처럼 꼭 필요할 때만 한꺼번에 정제합니다. 평상시 응답 속도는 빠르지만, 정제 전까지는 중복된 정보가 컨텍스트에 포함될 수 있습니다.
  - 그래서 ACE는 뭘로 함? -->

## 한계

1. 방법론의 구조상 context-heavy함(2x). 물론, 플레이북은 한 번 시스템에 로드되면 거의 변하지 않으므로, 이를 캐시에 저장해두고 재사용할 수 있음. 이를 통해 입력 토큰의 91.8%를 캐시에서 처리하여, 긴 컨텍스트를 다 넣으면서도 비용과 지연 시간을 물리적으로 줄이는 전략을 택함. 그럼에도 불구하고,
  - 물리적 컨텍스트 창의 한계: 아무리 캐싱 효율이 좋아도 모델이 수용할 수 있는 최대 토큰 수(Context Window)를 초과할 수는 없으며, 정보가 계속 쌓일 경우 결국 임의의 정제(Pruning)가 불가피해짐.
  - 주의 분산 및 노이즈 유입: 매 단계에서 전체 플레이북을 인지 범위에 두는 것은 모델에게 인지적 부하를 주며, 태스크와 무관한 전략이 섞여 있을 경우 핵심 정보 추출을 방해하는 'Lost in the middle' 현상이 발생할 위험이 있음
2. ACE의 Reflector는 사용자 명령이 요구하는 다수의 세부 전제 조건들이 실행 후의 실제 환경 상태와 정확히 일치하는지 대조하는 고품질 피드백 신호에 의존. 일반 사용자 환경에서 모든 일상적 태스크마다 이러한 정교한 상태 검증 로직을 미리 구축하는 것은 현실적으로 불가능. 특히, 에이전트의 편의성을 기대하는 사용자에게 이러한 수준의 피드백을 직접 요구하는 것은 부적절. 피드백 없으면 성능 떨어질 것임(가설).
3. 이전 경험에서 추출한 교훈들을 '모두' 하나의 '전략집'에 모아두고 매 태스크, 매 step을 해결해야할 필요성이 불분명. 많은 경우 현재 태스크, step, 또는 segment에 필요한 것은 과거 전체에서 얻은 모든 전략이라기보다, 일부 핵심 상태나 최근 몇 개의 관련 정보임. 각 step이나 segment의 실행 맥락에 따라 필요한 부분 전략들을 분리(credit assignment?)하는 게 우선이라는 생각. 현재 작업의 특정 스텝에 필요한 최적의 전략 조각만 선별해서 넣어주는 것이 아니라 플레이북 전체를 '일단 다 밀어넣는' 방식이라, 개별 지식 항목의 기여도를 정밀하게 관리하는 효율성이 떨어질 것임.
4. 공개된 ACE AppWorld 구현은 논문/README가 강조하는 counter-based refinement and deterministic de-duplication/merging보다는 append-only memory에 더 가깝다. 그 결과, 유사하거나 중복된 전략이 누적되거나, 특정 task에서만 유효한 지엽적 요령이 지속적으로 플레이북에 쌓일 수 있다. 이는 컨텍스트의 응집성과 일반화를 약화시키고, 장기적으로는 노이즈와 provenance-contaminated entries를 증가시켜 필요한 전략만 선별적으로 활용하기 어렵게 만들 수 있다. 

# Mistake Notebook Learning (MNL) https://arxiv.org/pdf/2512.11485

ReAct (Qwen3-8B) + ...
- 14.3% on normal
Qwen3-8B
- 12.5% on normal

DeepSeek-V3.2-Exp + ...
- 73.2% on normal
DeepSeek-V3.2-Exp
- 73.2% on normal


## 어떤 문제를 풀었는가?
evolving playbook / memory를 더 안정적이고 일반화 가능하게 업데이트하는 문제
1. 가짜 통찰(spurious insights) 위험. 잘못된 반성 결과(가짜 통찰)가 컨텍스트(플레이북)에 한 번 기록되면, 이후의 모든 작업에 독이 되어 성능을 갉아먹음(ACE에서도 스스로 지적했던 문제).
2. 저수준 요령의 기록. 개별 실패만 보면 “이 문제에서는 이 API를 써라” 같은 지엽적 요령만 남기 쉽고, 새로운 유사 작업으로 일반화되기 어렵다.

## 핵심 아이디어
1. instance-level이 아니라 batch-level로 실패한 태스크들을 클러스터링해서 전략을 추출. 두 가지 효과.
  - 가짜 통찰 억제(1/2). 공통적으로 반복되는 '진짜 원인'만 골라냄. 배치 단위의 검증을 통과한 정보만 '오답 노트(Mistake Notebook)'에 업데이트하므로, 신뢰도가 낮은 통찰의 생성을 억제.
  - 저수준 요령에서 '고수준 원칙'으로의 확장. 특정 사례를 넘는 subject-level / domain-level 원칙을 도출.
2. 일단 업데이트를 적용한 뒤, 성능이 개선된 경우에만 유지하고 아니면 이전 상태로 되돌림
  - 가짜 통찰 억제(2/2). 배치 단위 통찰에도 불구하고 시스템에 방해되는 메모리 업데이트 가능성 있음. 신뢰도 낮은 통찰이 메모리에 축적되어 시스템 전체를 망가뜨릴 위험을 줄임. "We provide a brief proof sketch explaining why batch-level (cluster-level) abstraction can reduce the probability of spurious updates under the accept-if-improves criterion."

## 한계
1. 성능 향상 미미함. vanila 에이전트랑 같은 경우도 존재.
2. 실패가 존재하는데도 notebook이 전혀 남지 않는 경우가 있다. DeepSeek-V3.2-Exp에서는 task success가 **73.2%**로, 약 26.8%의 실패 사례가 존재함에도 불구하고 Mem=0이다. 즉 최종적으로 채택된 notebook entry가 하나도 없다. 이는 실패가 있었음에도 일관된 subject-level 교훈을 추출하지 못했거나, 메모리 업데이트를 시도했더라도 batch 성능을 유의미하게 개선하지 못해 모두 롤백되었음을 뜻한다. 어느 쪽이든, MNL의 핵심인 memory update / utilization 메커니즘이 AppWorld에서는 충분히 효과적으로 작동하지 않았을 가능성을 시사한다.

# Trajectory-Informed Memory Generation for Self-Improving Agent Systems https://arxiv.org/pdf/2603.10600
# Towards Enterprise-Ready Computer Using Generalist Agent https://arxiv.org/pdf/2503.01861

ReAct (GPT-4.1) + Memory
Offline
- 73.2% on normal
- 64.3% on normal all-pass@3

ReAct (GPT-4.1)
Offline
- 69.6% on normal
- 50.0% on normal all-pass@3

## 어떤 문제를 풀었는가?

The inefficient success suggests an optimization tip: when emptying a cart with multiple items, use the bulk operation rather than iterating through individual removals. The failure-then-recovery suggests a recovery tip: when checkout fails due to missing payment method, verify payment in- formation is configured before retrying. The clean success suggests a strategy tip: before initiating checkout operations, systematically verify all prerequisites including cart contents, shipping address, and payment method availability.

Current approaches to agent improvement are inadequate for capturing these diverse learning opportunities.

- AWM [13], AgentRR [6]: 성공 위주 학습. “잘 된 경우를 재현하는 법”은 배울 수 있어도, 왜 실패했는지, 어떻게 복구했는지, 무엇이 비효율적이었는지 같은 정보는 체계적으로 반영하기 어렵다. 결과적으로 모델의 잠재력 경계를 넓히기보다는, 이미 잘 되는 패턴을 더 안정적으로 재현·활용(exploit) 하는 쪽에 가깝다.
- MNL: 실패 위주 학습. 이는 오류 교정에는 효과적일 수 있지만, 성공 전략이나 비효율 개선처럼 trajectory 전반의 다양한 학습 기회를 충분히 활용하지 못한다는 문제가 있다. 게다가 추상화 수준이 높아, 실행 현장에서 바로 재사용 가능한 구체적 behavioral guidance는 약해질 수 있다.
- ReasoningBank [9]: 성공과 실패를 모두 다루지만, 초점이 meta-cognitive reasoning strategy에 있다. 이런 방식은 고수준 추론 습관을 배우는 데는 적합하지만, 실제 agent 실행에서 반복적으로 나타나는 구체적인 행동 패턴, 복구 행동, 실행 수준의 팁을 포착하는 데는 거리가 있다. 즉, 추상화 수준이 높아질수록 실행 현장에서 바로 재사용 가능한 behavioral guidance는 약해질 수 있다
- ACE [16]: 성공과 실패를 모두 다루지만, 경험을 evolving playbook 형태로 단순히 누적한다. 이런 방식은 지식을 하나의 큰 문서처럼 계속 덧붙여 가는 구조이기 때문에, 정보가 점점 비대해지고 retrieval이 거칠어지며, 필요한 조각만 선택적으로 꺼내 쓰기 어려운 문제가 있다. 다시 말해, playbook이 커질수록 구조화된 memory entry 기반의 정밀한 검색과 통제가 어려워질 수 있다.

## 핵심 아이디어

1. **Trajectory Intelligence Extractor.** Trajectory를 semantic하게 분석해, 에이전트가 왜 그런 결정을 했는지, 어떻게 reasoning을 검증했는지, 어디서 self-correction이 일어났는지, 그리고 성공/실패 execution을 특징짓는 패턴이 무엇인지를 파악한다. 이는 AWM이나 AgentRR처럼 성공 trajectory를 단순 재현하는 수준을 넘어, trajectory 안에서 학습 가능한 패턴 자체를 읽어내기 위한 단계다.
2. **Decision Attribution Analyzer.** 분석된 패턴 중에서, 어떤 결정과 reasoning step이 실패·복구·비효율의 원인이었는지를 특정한다. 핵심은 실패만 보는 것이 아니라, 성공·실패·비효율적 성공 전반의 outcome을 모두 분석한다는 점이다. 즉, 결과를 단순 기록하는 것이 아니라 왜 그런 결과가 발생했는지 causal하게 짚어내기 위한 단계다.
3. **Contextual Learning Generator.** 그 원인 분석을 strategy (from clean success) / recovery (from failure or failure-then-recovery) / optimization (from inefficient success) tip으로 바꾼다. 이때 생성되는 tip은 generic한 고수준 원칙이 아니라, specific execution pattern에 grounded된 concrete behavioral guidance (actionable and contextually rich). AWM/AgentRR의 성공 편향, MNL의 실패 편향, ReasoningBank의 고수준 meta-cognitive abstraction을 모두 피하려는 설계. subtask 단위에서 tip 추출.
4. **Adaptive Memory Retrieval.** 이후 유사한 task에서 필요한 tip만 골라 prompt에 주입한다. ACE의 monolithic playbook 문제를 겨냥한 설계입니다. 논문은 retrieval이 semantic similarity 하나로 충분하지 않고, task type, domain, execution pattern 등 여러 차원(llm-guided retrieval)을 봐야 함.

## 한계
...

# Position: Agentic Evolution is the Path to Evolving LLMs https://arxiv.org/pdf/2602.00359

ReAct (Claude Haiku 4.5) + Online (실험에서는 offline이기는 함) Agentic Evolution
- 64% on normal
ReAct (Claude Haiku 4.5)
- 32% on normal

ReAct (Claude Sonnet 4.5) + Online (실험에서는 offline이기는 함) Agentic Evolution
- 90% on normal
ReAct (Claude Sonnet 4.5)
- 86% on normal

ReAct (GPT-5) + Online (실험에서는 offline이기는 함) Agentic Evolution
- 88% on normal
ReAct (GPT-5)
- 80% on normal

## 어떤 문제를 풀었는가?

train–deploy gap을 메우는 것. 기존 두 축인 training-time scaling과 inference-time scaling만으로는, 배포 후 실제 환경에서 드러나는 long-tail한 실패, 변화하는 요구사항, 운영 중 축적되는 경험을 충분히 반영하기 어렵. 그래서 세 번째 축인 deployment-time, *agentic evolution*을 제안. 배포 후 시스템의 persistent state—예를 들어 memory, tools, workflows, structured knowledge—를 대상으로 한 (1) goal-directed이면서 (2) automatic한 최적화 과정.
1. 경험을 무작정 누적하는 대신 어떤 변경이 실제로 지속적인 성능 향상에 기여할지를 따져가며 state를 수정해야 함.
2. 고정된 또는 휴리스틱 업데이트 규칙을 따르는 것이 아니라, 시스템이 스스로 실패와 기회를 분석하고(analyze), 변경 후보를 만들고(propose edits), 이를 검증·감사하고(audit), 최종적으로 채택하거나 롤백하는(commit/reject) agentic loop를 가져야 함.

## 핵심 아이디어

먼저 시스템이 원래 하던 대로 문제를 푼다(solver). 그다음 별도의 evolver (Claude Sonnet 4.5)가 그 실행 결과를 보고, 실패나 개선 기회를 분석한 뒤, 시스템의 persistent state를 어떻게 바꿀지 결정합니다. 여기서 persistent state는 memory, prompt, tool, workflow, structured knowledge 같은 배포 후에도 유지되는 외부 산물 전체를 뜻합니다. 이 evolver가 하는 일은 대략 네 단계입니다.

1. analyze: 무엇이 문제였고 무엇을 바꾸면 좋을지 진단
2. propose edits: memory 추가, workflow 수정, tool 교체 같은 변경 후보 생성
3. audit: 그 변경이 실제로 유효하고 안전한지 검증(unit tests)
4. commit / reject: 유지할지 롤백할지 결정

## 한계
1. 강한 상용 모델 하나에 의존한 orchestration입니다. 그래서 “일반적 프레임”이라는 주장에 비해, 프로토타입은 특정 강모델 의존성이 큽니다.

# ReMe (Remember Me, Refine Me) https://arxiv.org/pdf/2512.10696
성능 비교 불가. pass@4 사용함.

## 어떤 문제를 풀었는가?
기존 procedural memory가 대체로 “passive accumulation”, 즉 append-only 저장소에 머물러 있다고 비판

## 핵심 아이디어
에이전트가 과거 경험을 그냥 쌓아 두는 것이 아니라, 잘 뽑아내고(distill), 현재 task에 맞게 다시 쓰고(reuse), 쓸모없는 기억은 지우면서(refine) 스스로 진화
1. 성공/실패 trajectory에서 일반화 가능한 고품질 지식을 추출(comparative insight generation)
2. retrieved memory를 현재 task 요구에 맞게 적응적으로 활용.
  - retrieval을 semantic similarity (1차) 하나로 끝내지 않고, usage scenario indexing, reranking (2차)까지 활용.
  - memory를 “복붙”하는 게 아니라, 현재 과업의 제약에 맞춰 다시 편집
3. memory pool이 시간이 지나도 낡은 정보는 제거하고 유용한 정보는 강화하는 식으로 계속 최적화
  - memory entry의 utility를 추적하여 periodically pruning low-utility entries
  - 어떤 experience가 retrieval된 뒤 그 episode가 성공하면 그 entry의 utility가 += 1

## 한계
...








Developing agents that autonomously accomplish users' tasks within their personal digital workspaces remains a major goal. Toward this, notable approaches connect large language models (LLMs) to a user's environment through APIs, allowing them to directly perceive and manipulate the environment in service of completing assigned tasks. By acting in situ on users' behalf, these agents can take on operational overhead distributed across many tools and services, enhancing user productivity.

However, existing approaches largely rely on excessive user guidance that supplies task-critical contexts in user environments, undermining their agency and thereby the potential productivity gains. In particular, many assume users provide self-contained instructions upfront. Yet, this assumption is far from practice: users often omit critical personal contexts, as they are often distributed across their workspace and hard to specify upfront. While some works mitigate underspecification via explicit feedback from users---such as clarification, confirmation, and refinement---this dependence inherently introduces user burden and compromises agency, the very goal of autonomous agents.

To avoid this explicit supervision, studies let agents recover missing contexts directly from the personal workspace as they act. However, the resulting prolonged environment interaction often quickly disorients them, which is especially fatal tn the absence of user feedback to course-correct. Lacking initial certainty in user requests, agents are forced into longer interaction involving exploratory actions. As many agents operate in monolithic execution contexts (e.g., think-act-observe loop~\citep{react}), context becomes excessive and cluttered with massive low-level details and trial-and-error logs. With such chaotic contexts, agents often lose strategic coherence toward the overarching goal. 

While recent attempts employ active context compression to keep the agent's focus by retaining only what is essential, ...
aims to keep the agent's focus by retaining only what is essential, finding the right balance is challenging as all information---from high-level goals to potential future needs---competes within a single context window: aggressive compression risks context collapse by dropping critical information, whereas conservative compression hinders the agent's immediate focus by leaves the active context cluttered (e.g., with potentially necessary states for future steps).

이 문단을 learning으로 묶고, RL, memory 이렇게 도입(압축보단 학습).
Recent works address this disorientation via memory, yet remain limited by their monolithic execution contexts.
Second, memory-based approaches store and reuse past strategies or executable skills from past experiences to reduce repeated trial-and-error within the active context. However, strategy-resuing agents still struggle to process textual strategies alongside low-level APIs within a single, monolithic context, which is often exacerbated when retrieved memory is bloated and irrelevant 전략으로 혼재할 경우. 한편, 실행 가능한 스킬(Executable skills)을 저장하고 재사용하는 연구들(e.g., AWO, A-Evolve)은 이전에 성공적으로 수행한 프로시져를 replay 함으로써 ...하고자 하지만, 스킬이 replay 실패했을 때 살짝만 수정해서 쓰면 될 일을 처음부터 다시 하거나 다른 스킬을 찾는 등 이를 국소적으로 수정(local repair)하지 못하고 헤맨다. 또한, 스킬의 acquisition이 task별로 monolithic execution이 끝났을 때나 tracec 분석을 통해 이루어지기 때문에, 태스크 수행 중 얻은 부분 스킬을 다른 태스크에서만 활용할 수 있어서 기회를 놓친다.


context compression or memory-based self-improvement, yet remain limited by their monolithic execution contexts. 

First, while context compression aims to keep the agent's focus by retaining only what is essential, finding the right balance is challenging as all information---from high-level goals to potential future needs---competes within a single context window: aggressive compression risks context collapse by dropping critical information, whereas conservative compression hinders the agent's immediate focus by leaves the active context cluttered (e.g., with potentially necessary states for future steps). 

Second, memory-based approaches store and reuse past strategies or executable skills from past experiences to reduce repeated trial-and-error within the active context. However, strategy-resuing agents still struggle to process textual strategies alongside low-level APIs within a single, monolithic context, which is often exacerbated when retrieved memory is bloated and irrelevant 전략으로 혼재할 경우. 한편, 실행 가능한 스킬(Executable skills)을 저장하고 재사용하는 연구들(e.g., AWO, A-Evolve)은 이전에 성공적으로 수행한 프로시져를 replay 함으로써 ...하고자 하지만, 스킬이 replay 실패했을 때 살짝만 수정해서 쓰면 될 일을 처음부터 다시 하거나 다른 스킬을 찾는 등 이를 국소적으로 수정(local repair)하지 못하고 헤맨다. 또한, 스킬의 acquisition이 task별로 monolithic execution이 끝났을 때나 tracec 분석을 통해 이루어지기 때문에, 태스크 수행 중 얻은 부분 스킬을 다른 태스크에서만 활용할 수 있어서 기회를 놓친다.

도 존재한다. 그러나 이들은 



(ACE, MNL, CUGA (Trajectory-Informed Memory Generation), ReMe, AWO, SAGE, A-Evolve)

Alternatively, ``plan-and-execute'' approaches partition the execution context into manageable parts, but this risks brittle behavior due to over-committing to an initial plan that are often be based on incomplete information (speculation on user instructions)

However, ... memory 관리와 active context에 메모리 탑재하는 게 거칠다. 전략을 저장/재사용하는 approaches들은 predominantly accumulate experiences as unstructured, text-based ... Thus, the agent must still process these retrieved texts alongside low-level APIs within a single, monolithic context. 특히, ACE는 메모리를 단순히 축적만해서 memory bloat이 발생 가능하고, 메모리 전체를 context window에 넣기 때문에 불필요한 정보가 혼재하여 ...문제가 있음. Executable

Executable skill 류는 ... Executable-skill methods mitigate this only partially, as their skills are typically reused at the task or workflow level, 

rather than at the level of local execution contexts that recur both within and across tasks. 결정적으로, 이 연구들은 모두 context가 여전히 monolithic해서 ... 

태스크 

aim to shorten future execution contexts.

사용자 환경에 대한 지식, 전략, 스킬 등을 저장하고 재사용하므로써 ... execution context가 long-horizon해지는 것을 방지하여 lost in the middle을 줄이려고 함. 그러나, ...

Second, other studies propose memory-based self-improvement to familiarize the agent with the user's environment over time (ACE, MNL, CUGA, ReMe, AWO). By storing knowledge, strategies, and offline-merged tools, they aim to shorten future execution contexts. However, these approaches predominantly accumulate experiences as unstructured, text-based playbooks. As the agent encounters more edge cases, this monolithic memory bloats with spurious insights and highly localized tricks, ironically exacerbating the cognitive load during retrieval. Even when generating structured tool-calls, they heavily rely on offline logs or focus strictly on inter-task skill reuse across predefined scenarios, lacking the architectural flexibility to dynamically discover, isolate, and reuse skills within a single ongoing task (intra-task) when confronted with unexpected hurdles.

retain information needed later from the current execution context

fail to isolate future-contingent states cluttering the immediate context of the current step.

information needed later from the current execution context

may omit criticial information and is often limited because 당장에는 필요없지만 나중에 필요한 정보가 존재, where 미래의 정보로 인해 현재 상황에 집중이 어려움(여전히 헤매게 만듦)






<- RL 학습류를 문단2에서 해버리자. LOOP, SGE, SAGE.



As many approaches operate in a ReAct-style loop, interleaving reasoning, actions, and observations, 






To resolve this context bloat, recent works propose context management and memory-based self-improvement as complementary solutions, but both fall short.
First, context compression methods (e.g., Acon, PAACE) attempt to condense the active history. However, compression inherently risks omitting crucial preconditions or subtle domain rules. It also fails to cleanly separate temporal dependencies, tangling past actions with future requirements and causing the agent to hallucinate or wander. Alternatively, static "plan-then-execute" paradigms attempt to partition the execution context into manageable sub-goals upfront. Yet, this risks brittle behavior due to over-committing to an initial plan based on incomplete information (i.e., speculation on underspecified user instructions).
Second, other studies propose memory-based self-improvement to familiarize the agent with the user's environment over time (ACE, MNL, CUGA, ReMe, AWO). By storing knowledge, strategies, and offline-merged tools, they aim to shorten future execution contexts. However, these approaches predominantly accumulate experiences as unstructured, text-based playbooks. As the agent encounters more edge cases, this monolithic memory bloats with spurious insights and highly localized tricks, ironically exacerbating the cognitive load during retrieval. Even when generating structured tool-calls, they heavily rely on offline logs or focus strictly on inter-task skill reuse across predefined scenarios, lacking the architectural flexibility to dynamically discover, isolate, and reuse skills within a single ongoing task (intra-task) when confronted with unexpected hurdles.




attempts to manage the active context either compress entire reasoning trajectories (ACON, PAACE) or divide execution through a "plan-then-execute" paradigm. However, 

이 이슈 해결하기 위해 기존 연구들은 context management와 memory 기반 자가 개선이라는 complementary한 방식들을 제안함. First, context를 관리하려는 대부분의 연구는 compresses entire reasoning trajectories (ACON, PAACE), but ... [<- 중요한 맥락이 없어질 수 있음. 나중에 필요할지도 모르니 당장은 필요없어도 들고 다녀야함(PAACE). 현재 상황에 따라 필요한 정보, 불필요한 정보가 있는데 이에 대한 분리가 안돼서 현재 상황에 집중이 어려움(헤매게 만듦)]. Context 관리  

우리 에이전트는 ...


amortizes ... 사용자 환경에 대한 지식, 전략, 스킬 등을 저장. 그러나, ...


To address this, recent work has proposed two complementary directions: context management and memory-based self-improvement. 

Many approaches operate on a ReAct, but  


Memory-based approaches instead amortize experience across tasks by storing strategies, playbooks, or reusable skills. While valuable, they largely emphasize \emph{inter-task} reuse, and therefore can miss a more immediate source of efficiency: many long-horizon tasks repeatedly expose similar \emph{local contexts} within and across tasks, such as resolving a recipient, checking prerequisites, or grounding an entity before acting. Reusing skills only at the whole-task level leaves these finer-grained reuse opportunities underexploited.



+ 우리는 아예 상황에 따라 reasoning trajectories를 modular function 단위로 isolate 하니까 이런 걸 ACON이나 PAACE가 못한다는 점도 지적해줘야해



recursive context isolation을 통해 ... 그리고 execution context 사이에서 skill 전파가 이루어짐(뭐 당연히 task 사이에서도 이루어지고).


우리 연구를 먼저 프레이밍 해야할 듯. 인트로 쓰는 거 멈추고 다음 프레이밍에 대한 너의 이해로 재설명. recursive context isolation 느낌. c언어의 fork? context는 just-in-time 만들어지고(실행 중 필요에 의해) modular함. 그리고 태스크 단위 스킬 생성 및 inter task 스킬 reuse는 당연히 하지만, inter-context 스킬도 있는 느낌. 이렇게 하면 장점: the agent maintains long-horizon strategic coherence (↔ ReAct lost in the middle), avoids speculation (↔ static "plan-then-execute" paradigm, which risks brittle behavior due to over-committing to an initial plan that may be based on incomplete information.), and amortizes future effort more efficiently (↔ inter-task skill reuse), by keeping low-level behavior flexible, context-grounded, and reusable.




수도코드로 보면 다음과 같아. 이해해

function Solve(f, X, Π, Γ)
  𝜆 ← fn[X](Ø)
  Π ← Π[f ↦ 𝜆]
  𝜎 ← Run Π
  T ← {((Π, 𝜎), 𝛿) ↦ Ø : 𝛿 ∈ InitialActions(𝜆, 𝜎)}
  while ((Π, 𝜎), 𝛿 ← Explore(T)) ≠ ⊥ do
    𝜆 ← Π[f]
    𝜆′ ← Update(𝜆, 𝜎, 𝛿)
    if 𝜆′ indicates failure then
      Remove (Π, 𝜎), 𝛿 from T
      continue
    Π′ ← Π[f ↦ 𝜆′]
    while true do
      𝜎′ ← Run Π′
      if 𝜎′ indicates a call g(Y) for g ∉ Π then
        Π′, Γ ← Solve(g, Y, Π′, Γ)
      else
        T ← T ∪ {((Π, 𝜎), 𝛿) ↦ (Π′, 𝜎′)}
        A ← Critique(𝜆′, 𝜎′)
        if A indicates success then
          return Π′, Promote(𝜆′, Γ)
        T ← T ∪ {((Π′, 𝜎′), 𝛿′) ↦ Ø : 𝛿′ ∈ A}
        break
  return Π[f ↦ err], Γ






뭔가 recursive context isolation, just-in-time ..., adaptivity (local refinement search tree) 이런 느낌으로 framing하고 싶어. 이렇게 하면 장점이 "maintains long-horizon strategic coherence, avoids speculation, and amortizes future effort, by keeping low-level behavior flexible, context-grounded, and reusable." 장점이 더 있을수도 있고. 일단 내 의도 파악해서 framing 해봐. 그리고 한 가지 더 clarify하자면, 최상위 함수가 항상 planing이라든가 구조적 decomposition을 진행하지는 않아. 상황에 따라(사용자 쿼리에 따라) 전략을 선택해. 사용자 요청을 바로 해결할 수 있는 API가 존재할 것이라고 의심하고 API 탐색으로 시작할수도 있고, 쿼리가 좀 복잡하거나 그래서 API 호출로 바로 해결은 어려울 것이라고 의심 후 decomposition을 먼저 수행할수도 있어. 물론 local refinement search 코드에서 알 수 있듯이 atomic으로 시작하더라도 다른 브랜치에 compound가 남아있고, compound로 시작하더라도 atomic이 다른 브랜치에 남아있어.








내가 보고 있는 AppWorld 벤치마크는 아니지만, AlfWorld라는 벤치마크에서 주로 실험한 논문들에는 우리와 비슷한 '철학'을 이미 제안하고 있어. 나는 이 네 논문들의 철학이 우리의 철학과 유사도가 꽤 높은 것 같기도 하거든. 일단 각 논문들 꼼꼼히 읽고 어떤 점이 우리의 것과 다른지 분석해봐. 아주 엄격히. 아주 꼼꼼하게. 내 연구가 필요 없는 걸까? 나의 편에 일부러 서서 답변하지 말고, 리뷰어의 시선에서 답변해줘.
- https://arxiv.org/pdf/2405.17402
- https://arxiv.org/pdf/2411.13826
- https://arxiv.org/pdf/2601.14914
- https://arxiv.org/pdf/2510.23564



그런데 내가 준 4개 논문들은 alfworld라는 벤치마크에서 주로 평가되었어. appworld를 벤치마크로 쓰는 동네에서는 이 논문들이 인용조차 안되어 있단 말이지. 왜일까?

이 4개 논문들이 appworld 세팅에서는 잘 안 되는 appworld만의 고질적인 문제가 있어? appworld 동네에 논문 낸 저자들이, 내 눈에는 더 advanced한 context 관리인 recursive context isolation 방식을 몰랐을 것 같지는 않아. 근데 appworld쪽에는 recursive isolation 적용한 논문이 없다는 게 이상해.

내 연구랑 이 4개 논문들을 포지셔닝할 때, 방법론적 차이는 당연히 존재할 텐데, 내가 원하는 거는 이 네 논문들이 appworld와 같은 세팅에서는 풀지 못하는 고질적인 한계(failrue modes)를 우리가 풀었다는 느낌으로 포지셔닝하는 거야. 이 네 논문들 다시 꼼꼼히 읽고, 이 논문들을 appworld에 세팅에서 돌려보면 어떤 지점에서 망하거나 실패할 것 같은지 분석해봐

내 연구가 왜 필요한가를 리뷰어의 시선에서 엄격히 생각 중이야. 이미 4개 논문들과 메인 철학이 겹쳐보이거든. 물론 벤치마크가 다르지만. 그럼 나는 단순히 이 철학을 억지로 밀기보다는 아예 다른, 더 나은 철학을 제안한드는 뉘앙스여야 의미가 있을 것 같아. 기존 4개 논문들의 철학과 내 연구 철학의 본질적인 차이가 있을 것 같은 의심이야. 왜냐하면, 기존 철학은 alfworld에서 주로 평가되었거든. 이상하게도 appworld에서는 (나는 좋다고 생각하는) 이 철학을 적용한 논문은 찾지 못했어(없는 것 같아). 그러면 의심가는 거는 2가지야.
1. appworld 쪽 연구자들이 recursive, jit, ... 어쩌구 하는 철학을 전혀 모르고 있다. <- 이거는 믿기 힘들어. 설마 모를까 싶은거야.
2. alftworld에서는 4개 논문들의 철학이 유용하지만, 이 철학을 appworld에 그대로 적용하면 문제가 있다. <- 나는 이게 그나마 가능성 있다고 생각해. 그런데 나는 어쩌다보니 4개 논문들의 철학과 (얼핏 비슷해보이는, 또는 비슷한 게 맞는) 철학을 appworld에서 사용하고 있어. 그 말은 즉, 뭔가 결정적인 철학의 차이가 있지 않을까 싶은 거야. 그 결정적인 차이가 뭔가 벤치마크 차이에서 기인하는 failure modes에서 나타나지 않을까 하는거고.



1. The "Placeholder Trap" (환각된 추상화의 함정) - ReCode, REPL-Plan
  - 이들은 하향식(Top-down) 접근을 신봉합니다. 당장 어떻게 할지 모르면 일단 find_target_item(), book_ticket() 같은 추상적인 'Placeholder(자리 표시자)' 함수나 계획을 먼저 짜놓고, 나중에 그 내부를 재귀적으로 채워 넣습니다.
  - ALFWorld에서는 go_to_fridge()라는 추상적 계획이 하위의 walk와 open 액션으로 쉽게 매핑됩니다. 하지만 AppWorld에서는 에이전트가 마음대로 상상한 book_ticket()이라는 함수를 실제 API들(search_flights, get_user_payment, confirm_transaction 등)로 채워 넣으려고 할 때 **'API 현실(Reality)과의 격차'**로 인해 충돌합니다. 사용할 수 있는 API의 파라미터 제약이나 리턴 구조가 처음에 세운 추상적 계획과 맞지 않아, 재귀 트리의 밑바닥에서 영원히 에러를 뿜으며 갇히게 됩니다. (Speculation Failure)

작동 방식: 문제를 만나면 LLM의 '사전 지식(Prior)'에 의존하여 논리적으로 먼저 쪼갭니다. (예: "이 문제는 A, B, C 단계로 풀 수 있을 거야.") 그리고 각 단계를 재귀적으로 해결하려 듭니다.
철학적 한계: 이 방식은 **"환각(Hallucination) 기반의 하향식 설계"**입니다. AppWorld처럼 API 명세가 엄격한 곳에서는, LLM이 상상한 하위 함수 A가 실제 API로 구현 불가능한 경우가 허다합니다. 계획부터 세우는 이 철학은 AppWorld에서 필연적으로 실패합니다.

2. Lossy Context Squeezing (손실 압축에 의한 데이터 단절) - THREAD, CodeDelegator
  - 부모 에이전트의 컨텍스트 오염을 막기 위해, 자식 에이전트에게 아주 제한된 정보만 주고 독립적으로 문제를 풀게 한 뒤 '필요한 결과(주로 자연어 요약)'만 부모에게 돌려보냅니다.
  - AppWorld는 코드와 데이터 중심입니다. 자식 노드가 API를 호출해서 얻은 결과가 복잡한 JSON 객체이거나 암호화된 transaction_id일 때, 이를 자연어로 요약하거나 과도하게 추상화해서 부모에게 전달하면 부모는 다음 API 호출에 필요한 정확한 파라미터 값(Exact Values)을 상실합니다. 컨텍스트를 '격리'하려는 강박이, API 체이닝(Chaining)에 필수적인 '데이터의 정확한 전달'을 끊어버리는 치명적 결과를 낳습니다.

3. Rigidity in Error Recovery (경직된 에러 복구와 전략 수정 불가) - 4개 논문 공통
  - 하위 작업에서 에러가 나면, 해당 하위 작업 안에서 어떻게든(프롬프트를 다듬거나 재시도하여) 해결하려고 노력합니다.
  - AppWorld에서 API 호출이 실패하는 이유는 단순히 '코드를 잘못 짜서'가 아닙니다. "사용자의 잔액이 부족합니다", "해당 날짜에 예약 가능한 식당이 없습니다"처럼 근본적인 전략 수정이 필요한 피드백이 반환됩니다. 기존 논문들의 구조는 자식 노드가 이 에러를 안고 끙끙대다가 결국 Max_retries에 도달해 전체 시스템이 죽어버립니다. "잔액이 부족하면 다른 사람에게 돈을 빌린다"처럼 하위의 실패를 바탕으로 상위의 '전략 자체'를 유연하게 틀어버리는 백트래킹 능력이 없습니다.


Philosophy 1: "Grounding over Speculation" (추측이 아닌 근거 기반의 실행)

기존 연구들은 계획을 먼저 세우고 현실을 끼워 맞추려다 실패한다. 우리의 에이전트는 Opportunistic Execution을 통해 상황에 따라 즉각적인 API 탐색(Atomic)을 시도하며, 그 실제 실행 결과(Execution Trace)라는 확실한 근거(Grounding) 위에서만 필요할 때 구조적 분해(Compound)로 유연하게 선회한다. 우리는 존재하지 않는 API를 상상하지 않는다.

Philosophy 2: "Parametric Isolation with State Continuity" (상태 연속성이 보장된 매개변수 격리)

기존의 컨텍스트 격리는 데이터를 유실시킨다. 우리는 low_level_fn이 JIT(Just-in-Time)로 생성될 때, 부모의 거시적 '의도(Context)'는 격리하여 오염을 막되, 부모가 넘겨준 정확한 인자(Arguments, Y)와 리턴되는 '상태(State, σ)'는 코드 레벨에서 완벽하게 유지한다. 이는 API 체이닝이 필수적인 환경에서 유일하게 동작하는 고해상도 정보 전달 방식이다.

Philosophy 3: "Adaptive Strategy via Local Refinement Trees" (국소 정제 트리를 통한 적응형 전략)

단방향의 하향식 분해는 API 환경의 비가역적 실패에 취약하다. 우리는 탐색 트리(T)를 유지하여, 하위 레벨의 실패가 단순한 '코드 에러'인지 상위 레벨의 '전략적 불가능'인지 판단한다. 실패 시 하나의 가지(Branch)에 고집하지 않고, 트리에 대기 중인 다른 전략 브랜치로 백트래킹할 수 있는 진정한 의미의 적응성(Adaptivity)을 제공한다.


연구자님의 에이전트는 실행 주도적으로 결핍을 메우며 합성해 낸 하위 함수들을 글로벌 환경에 보존하고 다음 상호작용에 재사용합니다. 즉, 단순한 문제 해결을 넘어 **개인화된 작업 실행 및 유지(Task Execution and Retention)**를 수행하는 **"성장하는 시스템(Evolving System)"**입니다.






사용자의 요청이 단순해 보이면 **직관적으로 API를 찌르는 'Fast-path'**를 선택합니다.

이 시도가 실패하거나 모호할 때만 **구조적 분해를 시도하는 'Slow-path'**로 전환합니다.











"In THREAD, these sub- tasks are spawned “anonymously”, and cannot be re-used."



always prefer decomposition






continuation with isolated sub-contexts.



% 항상 분해: Plan-and-Execute (고정 계획) -> CodeDelegator (계획 변경 가능하지만 finer한 방향으로 더 decompose 강제됨.) ->
% 때에 따라 분해(?): ReCode (granularity control? w/ control flow structs) -> REPL-Plan
% On the other hand, agent with planner module (Figure 1(b)) separates high-level planning from low-level action using predefined structures. Such rigid boundaries impede agents from dynamically adjusting their decision granularity in response to 실행에 따라 드러나는 task complexities,

Static planning은 처음 수립한 계획을 실행 과정 내내 고정적으로 따르는 방식이다. 이 방식은 구조가 단순하고 추적이 쉽다는 장점이 있지만, 환경 변화나 예상치 못한 상황에 취약하다. 초기 계획 시점에 알 수 없었던 정보나 조건이 생겼을 때도 계획을 수정하지 않고 그대로 진행하기 때문에 실패 확률이 높다. 출처: https://ebbnflow.tistory.com/419 [삶은 확률의 구름:티스토리]

These tasks often require the planner to orchestrate a sequence of actions and decisions while maintaining context regarding original goals and progress. Furthermore, the initial architecture struggled with tasks involving multi-site control or data flow, copy/paste operations, and the manipulation of lists and loops. It also faced significant challenges in analyzing API responses, managing variables, and shortlisting relevant APIs for task execution.


planned speculation? over-reliant on assumptions, parametric knowledge. which is critical for our settings (strict API contracts, personal environments with user-specific contexts beyond LLMs knowledge)

child → parent 방향의 오염, parent → child 방향의 오염

1. Plan-and-Execute. 앞으로 뭐할지 계획을 세우고(고정) 그 다음 하나하나 해결.

-----

1. 가장 강한 차이: single-path retry/replan이 아니라, branch-preserving recovery search를 한다
2. 두 번째로 강한 차이: granularity uncertainty를 first-class object로 다룬다
3. 세 번째 차이: infeasibility를 structured upward signal로 다룬다 (이건 가능성은 있지만, CodeDelegator가 가장 가까운 prior라서 조심해야 해.)
4. 

deferred-commitment + branch-preserving refinement search + recursive helper synthesis
bidirectional commitment under uncertainty

문제를 쪼개는 구조(Tree 1)와
각 조각을 푸는 불확실성 탐색(Tree 2)
를 동시에 관리하거든.

Tree 1: where to isolate
Tree 2: how not to commit too early within the isolated context

a tree of contexts, each with its own tree of hypotheses





Tree 1 = semantic / contextual decomposition tree

단위: function / subproblem / skill

목적: 문제를 국소 context로 분리

생성 시점: just-in-time

질문: 무엇을 별도 context로 내려서 풀 것인가?

Tree 2 = local epistemic / repair search tree

단위: implementation hypothesis / recovery action / resolution mode

목적: 현재 context 안에서 어떤 해결 가설이 맞는지 탐색

생성 시점: 초기 branch + 실패 후 critique

질문: 이 context를 어떻게 풀 것인가?

이렇게 보면 된다.








1. planning 없음. child 결과 보고 난 다음에만 이후 태스크를 생각함. recursive isolated continuation. (THREAD, REPL-Plan)
2. planning 있음. (CodeDelgator, ReCode, 기타 planning 논문들 모두)
3. recursive하지는 않음. two-level 구조임. (CodeDelegator)
4. recursive하기는 하지만, 계속 쪼개거나 현재 context를 계속 retry하는 식의 trap 확률 높음. (THREAD, REPL-Plan, ReCode)
3. loop/branch같은 control flow structure를 고려하지 못함. (ReCode)
4. loop/branch같은 control flow structure를 사용할 수 있지만, 이거는 Executor만 가능하고 Delagator (즉, planner)는 불가능. (CodeDelegator)
5. recovery 없. (THREAD,)

잘못된 child output은 parent만 오염시키는 게 아니라, 그 parent에서 파생되는 이후 child들의 context에도 전파될 수 있어.

child → parent 방향의 오염, parent → child 방향의 오염

# REPL-Plan

act(...) 호출했는데 이게 불가능한 action이면 어떻게 됨? 
이 문제를 풀기 위해 A라는 subtask를 풀기로 하고 undefined function을 사용했는데, 이 function (즉, subtask)가 해당 환경에서 의도된대로 해결이 안 되면 어떻게 됨?
"Both REPL-Plan and THREAD ... are able to effectively change plans if there are environment issues (e.g. object is misplaced or mis-referenced)." <- 어떻게 계획을 바꾼다는 건지..

recovery는 해당 REPL 안에서만 해야함. Parent REPL이 실수로 불가능한 subtask를 주면, 그 안에서 갇히게 됨. 가능한 subtask이더라도, trial-and-error는 monolithic recovery trace에서 이루어짐. error recovery를 위한 메커니즘은 따로 없고 llm이 보고 알아서 하는 거임. 롤백도 없음. 이전 trial-error가 계속 쌓임. 여러 가지 해결 방식에 대한 격리가 없어서 context가 더러워질 수 있음. failure loop에 빠질수도 있음(as reported). 우리는 child 함수에서 refinement tree를 유지하면서 recovery도 context도 효과적으로 isolation함. context가 섞이는 걸 막음. 브랜치. 그리고 여러 격리된 trial-and-error에도 실패할 경우 child가 해당 subtask의 infeasibility를 인지하고 parent에게 notify할 수 있음. On notification, parent는 마찬가지로 refinement tree를 구성하며 격리된 recovery를 수행함.

또한, 불가능한 subtask REPL로 한 번 들어오면, 에이전트는 2가지 선택지 뿐임. (1) 위로 올라가는 길: 말도 안되는 답변이라도 parent한테 리턴하기. (2) 아래로 내려가는 길: 태스크를 더 쪼개서 child를 spawn하기. 전자는 그 자체로 시스템을 망가뜨리고, 후자는 어차피 불가능한 subtask의 subtask이므로 여전히 불가능함. 결국, 틀린 답변을 하거나, placeholder trap에 갇히는 길밖에 남지 않게됨.

REPL-Plan permits direct atomic actions, but it is structurally biased toward recursive decomposition. Rather than committing late between direct action and decomposition, REPL-Plan treats recursive subtask abstraction as a primary mechanism.

# CodeDelegator
우리 방식의 2-level 버전. level 1에서는 compound 전략으로 시작(atomic 브랜치 없음). update는 compound를 더 잘게 쪼개는 방향으로 고정.
비판: always prefer decomposition. Replan mechanism prefers finer-grained decomposition (근거: "If a sub-task later proves too complex, the Replan mechanism allows dynamic re-decomposition." "The decomposition is guided by two principles. Atomicity: Each sub-task should be small enough to complete within a single Coder session.").

# ReCode
1. for/while/if/ 이런 control flow를 다루기 힘들 듯 한데. "do not place placeholder functions inside loop or condition structures."
2. state isolation은 안 되는 듯 한데... "ReCode implements context management through a unified variable namespace that persists throughout task execution"
3. 애초부터 infeasible하게 decompose헸가니 contract가 잘못 잡힌 경우라면 망할 것 같은데. 계속 retry할테니까. "Upon execution failure, the system re-invokes the policy with the original placeholder and the error traceback as additional context."
4. 백트래킹은 없나(위로 올라가기)? 뭔가 계속 쪼개는 거에 trap될 듯 한데. maximum recursion depth는 존재하는 것 같은데, 그럼 이 maximum depth 도달하면 어떻게 한다는거지..? "We impose a maximum recursion depth of 10 for our benchmark tasks, chosen as a conservative upper bound above the empirically optimal depth (in Section 4.2), balancing planning complexity with guaranteed termination."


action space의 크기나 복잡성이 차원이 다른 것 같음. alfworld는 action이 적음. primitive한지 아닌지 체크가 단번에 가능함. 근데, appworld는 달라. 방대한 api documentation을 뒤져보기 전까지는 이게 primitive 태스크인지 아닌지 규명이 어려움. 잘못된 선택은 결과가 처참함. 어떤 문제는 LLM이 보기에는 아주 복잡해 보이지만 API 단 한 방(Atomic)으로 끝날수도 있음. 오히려 쪼갰을 때 쪼개진 부분에 대해서는 api가 없어 해결이 불가능해지는 trap에 갇혀버릴 수 있음. 반대로 쉬워 보이지만 수많은 API를 조합해야 하는 경우도 있음. 

ALFWorld의 "일단 쪼개고 본다(Top-down forced decomposition)"는 철학은 AppWorld에서 불필요한 복잡도만 가중시킵니다.










지금까지 기존 비슷한 연구들과 비교를 위한 디스커션을 꽤 많이 했는데, 빠짐없이, 체계적으로 정리해줘. 우리 연구의 필요성을 리뷰어에게 납득시켜야돼. 다시 말하지만, Related Works를 위한 비교가 아니야. Introduction을 위한 비교야. 지금 Introduction을 바로 작성하라는 말은 아니고, 나중에 작성할 때 참고하기 위해 체계적인 정리를 요구하는 거야. 비교를 할 때, "기존 연구는 A가 없는데(A를 안 하는데) 우리는 A가 있다(A를 한다)" 이런식으로 비교하지마. "기존 연구는 A가 없는데(A를 안 하는데) 우리는 A가 있다(A를 한다). A를 하는 것은 이러이러한 이유로 중요하다." 이런식으로 왜 A까지 필요한지도 설명해야해. 아래 리스트업한 논문들 반드시 포함하고, 그 외 planning 계열의 agent 논문들 및 recursive context isolation을 다루는 논문들도 대표적인 것들 위주로 더 검색해서 추가해줘.

- THREAD (https://arxiv.org/pdf/2405.17402)
- REPL-Plan (https://arxiv.org/pdf/2411.13826)
- CodeDelegator (https://arxiv.org/pdf/2601.14914)
- ReCode (https://openreview.net/pdf?id=h4DNjtyRRA)
- CUGA (https://arxiv.org/pdf/2503.01861)
- Plan-and-Act (https://arxiv.org/pdf/2503.09572)
- 그 외 planning 계열의 agent 논문들 및 recursive context isolation을 다루는 논문들

정리할 때, 일단 각 논문별로 비판하면서 '우리한테는 있는 이러이러해서 중요한 무언가가 각 논문에는 없다'는 식으로 한계점들을 지적해줘. 몇몇 한계점들은 리뷰어 입장에서 significant하지 않다고 판단될수도 있지만, 포함해줘. 대신, insignificant한 부분은 명시적으로 표시해줘. 그리고 당연하게도, 여러 논문들은 해당 한계를 공유할 수 있어. 서술 상 중복 같아도 일단 논문별로 분리해서 작성해줘. 그 다음, 각 한계를 축으로 해서 이 한계를 공유하는 논문들을 묶어줘. 비교 테이블도 작성해줘. 한계점 축들을 중요도 순으로 정렬도 해줘.

내가 명시적으로 요구한 사항 외에도 너의 생각에 나중 introduction 작성에 도움이 될 분석이나 내용이 있으면 자유롭게 추가해도 돼. 최소한 내가 요구한 사항들은 빠뜨리지마.






Continuation with recursively isolated subtask contexts

--------------------------------------------------
In ambiguous environments, planned steps can be wrong for multiple different reasons.

- decomposition-first bias. If the environment offers “one-shot” atomic operations (e.g., a single API call encapsulates what looks like a multi-step human procedure), the decomposition-first bias can create unnecessary, sometimes infeasible, intermediate subtasks.

w/o error handling. Parent→child framing errors and child→parent return “confident but wrong” propagate throughrecursion.


1. Infeasible subtask contracts and wrong decomposition framing.
The agent commits to a subtask whose contract does not match what the environment can actually support (wrong API, missing required state, “subproblem that doesn’t exist”). An infeasible subtask causes repeated failures, wasted interactions, and potentially harmful partial actions.
  - THREADS [A]
  - REPL-Plan [A] exacerbated [C]
  - CodeDelegator [D]
  - ReCode [F]
  - Plan-and-Act [?]
  - LATS [?]
  - AdaPlan [?]

2. 







## THREADS
A. no error handling. misinformation becomes part of the parent context and can propagate into later children. this can produce either (i) “confident but wrong” continuation (return something), or (ii) looping.
B. without control flow structs.

## REPL-Plan
A. no error handling. misinformation becomes part of the parent context and can propagate into later children. this can produce either (i) “confident but wrong” continuation (return something), or (ii) looping.
C. A child context, if previously spawned, continues execution history from previous, accumulating trial-and-error (“context pollution”)

## CodeDelegator
D. does handle errors. retry or replan. however, if initial decomposition is wrong, the decomposition-first bias can cause retry loop or decomposition loop (for both contract invention can still happen).
E. granularity control is just more decomposition on errors (replan).

## ReCode
B. without control flow structs.
F. does handle errors. retry only. however, if initial decomposition is wrong, cannot fix.

## CUGA
...

## Plan-and-Act

The paper’s analysis notes that a base Planner not trained/grounded to specific websites can produce suboptimal plans that confuse the Executor

## LATS: Language Agent Tree Search
...

## AdaPlan: Adaptive Planning from Feedback with Language Models








Isolating execution horizons is a promising approach for maintaining long-horizon coherence, yet current methods suffer from brittle isolation granularity. Early reactive approaches (e.g., THREAD, REPL-Plan) treat context isolation as an implicit byproduct of step-wise execution. By reactively spawning new contexts upon encountering immediate triggers (e.g., undefined functions) without explicit granularity control, they fail to represent task uncertainty and lack the adaptivity to contextualize the depth of problem-solving.

Conversely, recent top-down planning methods (e.g., CodeDelegator, ReCode) attempt explicit granularity control but fall into the opposite trap: they resolve granularity uncertainty too early and too rigidly. By committing to a static decomposition before observing execution feedback, agents often become trapped in "planning harder on the wrong structure." This premature commitment inevitably leads to fatal failure modes, such as infinite retry loops on non-existent subproblems or the generation of overly fine-grained, unexecutable tasks.




0) Choose a code-generation option 𝑺 for the current context.
1) Based on 𝑺, generate a code for the current context, mixing placeholders with executables.
2) Execute the context.
3) When execution encounters a placeholder, pause execution, spawn a child context, and go to 0) with this as the current.
4) When execution encounters the end of the current context or an error, evaluate the states.
  (a)	ends “as expected”: go to 2) with the parent context as the current, passing the result.
  (b)	otherwise: Generate zero or more new option(s) for the current context and go to 0).

User guidance (✗) vs. environment exploration
- Requesting user feedback introduces user burden, undermining agency.
  - User: My manager emailed our weekly standup time has changed. Set my phone alarm 10 minutes before the meeting.
  - Agent:
    - What is email address of your manager?
    - What is the email title?

User guidance vs. environment exploration (✓)
- Let agents recover missing contexts from workspaces as they act.
- User: My manager emailed our weekly standup time has changed. Set my phone alarm 10 minutes before the meeting.
  - Agent:
    - Needs to identify email address of your manager.
    - Needs to find and read the email contents.





Agents must probe contexts from the workspace
At the same time, they must make progress on the end goal
Execution trace becomes longer, more tangled
Agents lose focus toward the goal



Compressing execution contexts
- Retain only important information in the active window
- But LLMs often struggle to assess which states are worth preserving
  - Context collapse[1]: Agents irreversibly discard too much
  - Over-retention[2]: Active context can remain cluttered with those that are not immediately useful
    - E.g., those that are potentially necessary in future steps


Isolating execution contexts
- Isolate execution into subtasks
- Agents now solve tasks in isolated local contexts
  - can focus strictly on local objectives without polluting the full execution trace
