Feature: Resuming a loop
  As the orchestrator agent, I resume a run whose loop ended short or that I stopped, so that the
  loop rounds already done are not paid for twice.

  @flow
  Scenario: A raised cap continues a capped loop
    Given the loop `green` ended `capped` after loop round 4
    And I changed `max_rounds` of the loop `green` to 6 in the workflow module
    When I run `ohflow run --resume <run-id>`
    Then `fixer.r01` to `fixer.r04` are recorded `cached`
    And the engine decides loop round 4 again from the numbers in the run log, runs no check command for it, and writes `continue`
    And `fixer.r05` starts

  @flow
  Scenario: A resume restarts the stall count and keeps the count of loop rounds
    Given the loop `green` ended `stalled` after loop round 3 of 4
    When I run `ohflow run --resume <run-id>`
    Then the engine writes `loop_decided` for loop round 3 again as `continue`, with a stall count of 0
    And `fixer.r04` starts
    And the loop ends `capped` when the stop command still exits 1 after loop round 4

  @flow
  Scenario: A resume keeps a loop that ended done
    Given the loop `green` ended `done` at loop round 2, and a phase after the loop failed
    And the loop `green` is unchanged in the workflow module
    When I run `ohflow run --resume <run-id>`
    Then `fixer.r01` and `fixer.r02` are recorded `cached`, and `fixer.r03` and `fixer.r04` stay `skipped`
    And the engine runs no check command of the loop `green`
    And the failed phase after the loop starts again

  @flow
  Scenario: A changed check command measures again from the last loop round that ran
    Given the loop `green` ended `stalled` after loop round 3
    And I changed `progress_cmd` of the loop `green` in the workflow module
    When I run `ohflow run --resume <run-id>`
    Then the engine runs both check commands at the HEAD of the loop's worktree before any step of `fix.r04` starts
    And it writes their result as the new baseline in `loop_decided` for loop round 3, and decides from that baseline on

  @flow
  Scenario: A killed loop round pauses the run without a decision
    Given I ran `ohflow kill --run <run-dir> --step fixer.r03 --reason "the trail is flat"`
    When `fix.r03` settles
    Then the engine runs neither check command and writes no `loop_decided` event for loop round 3
    And the run finishes `paused`
    And a later `ohflow run --resume <run-id>` starts a new attempt of `fixer.r03`
