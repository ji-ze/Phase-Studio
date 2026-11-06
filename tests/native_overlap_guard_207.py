"""Permit only the reviewed native-group dispatch, retaining all arithmetic pins."""
import ast


def restore_estimated_dispatch(node):
    argument=ast.parse('def f(native_grouping: object = None): pass').body[0].args
    assert ast.dump(node.args.args[-1])==ast.dump(argument.args[0])
    assert ast.dump(node.args.defaults[-1])==ast.dump(ast.Constant(None))
    node.args.args.pop();node.args.defaults.pop()
    expected=ast.parse('groups = native_grouping.groups_for(current, cell, wavelength, separation_factor) if native_grouping is not None else assign_powder_overlap_groups(current, cell, wavelength, separation_factor)').body[0]
    found=[statement for statement in node.body if ast.dump(statement)==ast.dump(expected)]
    assert len(found)==1
    index=node.body.index(found[0])
    node.body[index]=ast.parse('groups = assign_powder_overlap_groups(current, cell, wavelength, separation_factor)').body[0]
