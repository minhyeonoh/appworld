import ast
import builtins

from scalpel.cfg import CFGBuilder

_BUILTIN_NAMES = set(dir(builtins))


def _walk_shallow(stmt):
    """Walk AST nodes in a statement, skipping bodies of compound statements."""
    if isinstance(stmt, ast.If):
        yield from ast.walk(stmt.test)
    elif isinstance(stmt, ast.For):
        yield from ast.walk(stmt.target)
        yield from ast.walk(stmt.iter)
    elif isinstance(stmt, ast.While):
        yield from ast.walk(stmt.test)
    elif isinstance(stmt, ast.Try):
        pass  # handlers/body are separate blocks in CFG
    else:
        yield from ast.walk(stmt)


def _get_block_calls(block):
    """Extract non-builtin function call names from a block's statements via AST."""
    calls = []
    for stmt in block.statements:
        for node in _walk_shallow(stmt):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                name = node.func.id
                if name not in _BUILTIN_NAMES:
                    calls.append(name)
    return calls


def _is_in_loop(block, all_blocks):
    """Check if a block is part of a cycle (loop) in the CFG."""
    visited = set()
    queue = [link.target for link in block.exits]
    while queue:
        curr = queue.pop(0)
        if curr.id == block.id:
            return True
        if curr.id in visited:
            continue
        visited.add(curr.id)
        for link in curr.exits:
            queue.append(link.target)
    return False


def can_reach_exit_without_other_calls(start_block, all_call_blocks, final_blocks):
    """
    특정 블록(start_block)에서 출발하여,
    다른 헬퍼 함수 블록을 거치지 않고 함수의 종료 지점에 도달할 수 있는지 BFS로 확인합니다.
    """
    if start_block in final_blocks or not start_block.exits:
        return True

    visited = set()
    queue = [link.target for link in start_block.exits]

    while queue:
        curr = queue.pop(0)

        if curr.id in visited or curr in all_call_blocks:
            continue

        visited.add(curr.id)

        if curr in final_blocks or not curr.exits:
            return True

        for link in curr.exits:
            queue.append(link.target)

    return False


def is_single_terminal_call_block(source_code: str, target_func_name: str) -> bool:
    # 1. CFG 생성
    builder = CFGBuilder()
    cfg_module = builder.build_from_src("orchestration_module", source_code)

    # 2. 타겟 함수의 CFG 추출
    func_cfg = None
    for func_key, cfg in cfg_module.functioncfgs.items():
        if isinstance(func_key, tuple):
            if target_func_name in func_key:
                func_cfg = cfg
                break
        elif isinstance(func_key, str):
            if func_key == target_func_name or func_key.endswith(f".{target_func_name}"):
                func_cfg = cfg
                break

    if not func_cfg:
        available_funcs = list(cfg_module.functioncfgs.keys())
        raise ValueError(f"'{target_func_name}' 함수를 찾을 수 없습니다. (현재 인식된 함수들: {available_funcs})")

    all_blocks = list(func_cfg.get_all_blocks())

    # 3. 헬퍼 함수(Call)가 포함된 블록들 식별 (AST 기반, builtin 제외)
    call_blocks = set()
    for block in all_blocks:
        if _get_block_calls(block):
            call_blocks.add(block)

    if not call_blocks:
        return False

    # 4. 'Last Call Block' 후보 찾기 (루프 내 블록 제외)
    last_call_blocks = set()
    for block in call_blocks:
        if _is_in_loop(block, all_blocks):
            continue
        if can_reach_exit_without_other_calls(block, call_blocks, func_cfg.finalblocks):
            last_call_blocks.add(block)

    # 5. 마지막 헬퍼 함수 블록이 정확히 1개이면 True, 2개 이상이면 False
    return len(last_call_blocks) == 1


# ==========================================
# 테스트 용도 실행 코드
# ==========================================
_TESTS = [
    ("No calls", """
def f():
    x = 1
    return x
""", False),
    ("Single call", """
def f():
    return foo()
""", True),
    ("Sequential calls", """
def f():
    a = foo()
    b = bar(a)
    c = baz(b)
    return c
""", True),
    ("Diverging branch at end", """
def f(x):
    a = setup()
    if x:
        return finish_a(a)
    else:
        return finish_b(a)
""", False),
    ("Branch then converge", """
def f(x):
    if x:
        a = path_a()
    else:
        a = path_b()
    return finish(a)
""", True),
    ("Nested loop", """
def f(items):
    for group in items:
        for item in group:
            process(item)
""", False),
    ("Loop then terminal", """
def f(items):
    for item in items:
        process(item)
    return finalize(items)
""", True),
    ("While loop", """
def f():
    while True:
        result = poll()
        if result:
            break
""", False),
    ("Try/except converge", """
def f():
    try:
        x = risky()
    except:
        x = fallback()
    return finish(x)
""", True),
    ("Try/except diverge", """
def f():
    try:
        return risky_finish()
    except:
        return safe_finish()
""", False),
    ("Builtins only", """
def f(x):
    a = len(x)
    b = str(a)
    return int(b)
""", False),
    ("Builtins + one helper", """
def f(x):
    a = len(x)
    b = process(a)
    c = str(b)
    return c
""", True),
    ("Early return diverge", """
def f(x):
    if not x:
        return handle_empty()
    return handle_normal(x)
""", False),
    ("Loop + post-loop call", """
def f(items):
    results = []
    for item in items:
        results.append(transform(item))
    return aggregate(results)
""", True),
    ("Dotted call (not a helper)", """
def f():
    return app.send_message(x)
""", False),
    ("Nested call args", """
def f():
    return outer(inner(x))
""", True),
    ("Comprehension in loop", """
def f(items):
    for batch in items:
        results = [process(x) for x in batch]
    return results
""", False),
    ("Conditional call no else", """
def f(x):
    if x:
        result = compute(x)
    return result
""", True),
    ("Multiple calls same block", """
def f():
    a = foo()
    b = bar()
    return b
""", True),
    ("Loop call + post terminal", """
def f(items):
    for item in items:
        validate(item)
    result = process_all(items)
    return finalize(result)
""", True),
    ("While with condition call", """
def f():
    while check():
        do_work()
    return done()
""", True),
    ("For loop, call in iter", """
def f():
    for x in generate():
        process(x)
    return finish()
""", True),
    # --- Original test cases ---
    ("Loop with branch (original)", """
def create_splitwise_expense(person_entry, combined_extras):
    for entry in person_entry:
        has_venmo = check_venmo(entry)
        if has_venmo:
            res1 = send_venmo(entry)
            print(res1)
        else:
            res2 = create_split(entry)
            print(res2)
""", False),
    ("Loop no branch (original)", """
def create_splitwise_expense(person_entry, combined_extras):
    for entry in person_entry:
        has_venmo = check_venmo(entry)
        res1 = send_venmo(entry)
        print(res1)
""", False),
    ("Converge (original)", """
def create_splitwise_expense(person_entry, combined_extras):
    has_venmo = check_venmo(person_entry)
    if has_venmo:
        payment_data = prepare_venmo(person_entry)
    else:
        payment_data = prepare_splitwise(person_entry)

    final_result = send_payment(payment_data)
    print(final_result)
""", True),
    ("Return call (original)", """
def create_splitwise_expense(person_entry, combined_extras):
    has_venmo = check_venmo(person_entry)
    if has_venmo:
        payment_data = prepare_venmo(person_entry)
    else:
        payment_data = prepare_splitwise(person_entry)

    return send_payment(payment_data)
""", True),
]


if __name__ == "__main__":
    all_pass = True
    for name, code, expected in _TESTS:
        # Extract function name from code
        for line in code.strip().splitlines():
            if line.startswith("def "):
                fn_name = line.split("(")[0].replace("def ", "").strip()
                break
        result = is_single_terminal_call_block(code, fn_name)
        status = "OK" if result == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {status}: {name} → {result} (expected {expected})")

    print()
    print("All passed!" if all_pass else "SOME FAILED")
