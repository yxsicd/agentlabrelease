# Pinned source and extracted-sample boundary

Source: openharmony/applications_calendar at
`a44b0ad503f69e50943520a0ea569c9cfcb09a57` (Apache-2.0).
Inspect these original paths at that exact commit:

- features/repeatrule/RecurrenceParser.ets: recurrence parsing orchestration.
- features/repeatrule/ruleparse/ParseByMonthDay.ets: numeric-list boundary.
- features/repeatrule/ruleparse/ParseByWeekDay.ets: weekday/ordinal parsing.
- common/src/main/ets/adapter/RecurrenceImportantAdapt.ets: application adapter.
- product/entry/src/ohosTest/ets/test/repeatrule/ParseByMonthDay.test.ets
- product/entry/src/ohosTest/ets/test/repeatrule/ParseByWeekDay.test.ets

Locate actual declarations and original tests before assuming behavior from a
filename. The existing AL Calendar sample extracts selected parser bodies into
RecurrenceParserAdapter.ets and supplies a small ArkUI inspector. Later adapter
corrections and controls are sample evolution, not upstream Calendar patches.
The persistence task below concerns that sample's Index/EntryAbility, not a
claim that the upstream Calendar application's entire UI has been verified.

Seed candidates include strict versus prefix integer recognition, atomic invalid
lists, bare weekday versus explicit zero ordinal, and persistence of draft versus
last evaluated state. Each candidate needs a source-grounded independent oracle
and actual accepted input point before it becomes a runnable assessment.
