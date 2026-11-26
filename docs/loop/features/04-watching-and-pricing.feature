Feature: Watching and pricing a loop
  As the orchestrator agent, I see each loop decision where I watch the run, and I see the price of
  a loop round before the run starts, so that I can size the cap and judge the loop between loop
  rounds.

  @flow
  Scenario: watch prints each loop decision
    Given the loop `green` has `max_rounds=4`
    When the engine writes `loop_decided` with `continue` for loop round 3 and the trail 14, 9, 7, 5
    Then `ohflow watch` prints `loop green: loop round 3 of 4, progress 14 -> 9 -> 7 -> 5, continue`

  @flow
  Scenario: status and the dashboard show the loop rounds that did not run
    Given the loop `green` ended `done` at loop round 2 of 4
    When I run `ohflow status`, or open the run's dashboard
    Then `fixer.r03` and `fixer.r04` show as `skipped` with the reason "loop green ended done at loop round 2"
    And the dashboard shows the two of them as one row

  @flow
  Scenario: estimate prices one loop round and the cap
    Given the history holds finished attempts of the role, harness executor and model of `fixer`
    When I run `ohflow estimate --workflow <module>`
    Then it prints one line for the loop `green` with the price of one loop round and the price of 4 loop rounds
    And the run's total counts the loop at its cap
    And when the history holds finished runs of a loop named `green`, the line adds the median number of loop rounds they ran

  @flow
  Scenario: A pilot runs one loop round of each loop
    Given my workflow declares units and the loop `green`
    When I run `ohflow run --pilot`
    Then the pilot runs `fix.r01` and no later loop round of `green`
    And `pilot.json` projects the loop `green` at its cap of 4 loop rounds

  @flow
  Scenario: The run's summary carries every loop's end
    Given the loop `green` ended `stalled` after loop round 3
    When the run finishes
    Then `summary.json` lists the loop `green` with the decision `stalled`, 3 loop rounds run and the trail
    And the exit report shows the same

  @flow
  Scenario: A judge reads the trail of a loop in its milestone
    Given a milestone workflow holds the loop `green`
    When the campaign controller writes the judge packet
    Then the packet has a section for the loop `green` with each loop round's decision, its progress number and the stop command's exit code
