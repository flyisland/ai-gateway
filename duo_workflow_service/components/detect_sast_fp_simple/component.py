def attach(graph, entry_node, exit_node):
    graph.add_node(entry_node, start_fp_detect_component)
    graph.add_node(exit_node, end_fp_detect_component)
    graph.add_edge(entry_node, exit_node)
    return entry_node

async def start_fp_detect_component(state):
    # Minimal node logic for component
    return state

async def end_fp_detect_component(state):
    # Minimal node logic for component
    return state 