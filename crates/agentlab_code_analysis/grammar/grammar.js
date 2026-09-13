const ArkTS = require('./upstream/common/define-grammar');
module.exports = grammar(ArkTS, {
  name: 'agentlab_arkts',
  rules: {
    pair: ($, previous) => choice(previous, seq(
      field('key', $._property_name), ':', field('value', $.arkui_style_block)
    )),
    // ArkUI stateStyles object values contain leading-dot modifier chains.
    // Keep ordinary object expressions on the inherited grammar path.
    arkui_style_block: $ => seq('{', repeat1(seq($.leading_dot_expression, optional(';'))), '}'),
  },
});
