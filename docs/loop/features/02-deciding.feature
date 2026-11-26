Feature: The loop decision
  As the orchestrator agent, I get a decision from the engine after every loop round, made from two
  commands and never from an agent's message, so that a loop ends on evidence and its last
  possible loop round is one I named before the run.

  Background:
    Given the loop `green` runs the phase `fix` with `progress_goal="down"`, `stall_rounds=2` and `max_rounds=4`

  @flow
  Scenario: The engine measures before the first loop round
    When the run reaches the loop `green`
    Then the engine runs the stop command and the progress command in the loop's worktree before any step of `fix.r01` starts
    And the run log holds a `loop_decided` event for loop round 0 with the stop command's exit code and the progress number
    And `loops/green/r00/stop.log` and `loops/green/r00/progress.log` in the run directory hold the two outputs

  @flow
  Scenario: A loop whose stop command already passes runs no loop round
    Given the stop command exits 0 at the loop's base
    When the run reaches the loop `green`
    Then `loop_decided` for loop round 0 reads `done`
    And every step of `fix.r01` to `fix.r04` is recorded `skipped` with the reason "loop green ended done at loop round 0"
    And the first phase after the loop starts

  @gate:repetition
  Scenario: The stop command ends the loop, and an agent's message does not
    Given the agent of `fixer.r02` ends with the message "all tests pass, the loop can stop"
    And the stop command exits 1 after `fix.r02` settles
    When the engine decides loop round 2
    Then `loop_decided` reads `continue`
    And `fixer.r03` starts

  @flow
  Scenario: A passing stop command ends the loop, and the run goes on
    Given the stop command exits 0 after `fix.r02` settles
    When the engine decides loop round 2
    Then `loop_decided` reads `done`
    And `fixer.r03` and `fixer.r04` are recorded `skipped` with the reason "loop green ended done at loop round 2"
    And the first phase after the loop starts

  @gate:repetition
  Scenario: Two loop rounds without improvement end the loop
    Given the progress command printed 14 at loop round 0 and 9 after loop round 1
    And it prints 9 after loop round 2 and 11 after loop round 3
    And the stop command exits 1 after each of them
    When the engine decides loop round 3
    Then `loop_decided` reads `stalled` with the trail 14, 9, 9, 11
    And `fixer.r04` and every step after the loop are recorded `skipped`
    And the run finishes `failed`, and the exit report names the loop, the decision and the trail

  @gate:repetition
  Scenario: The cap ends the loop
    Given the progress number fell after every loop round
    And the stop command exits 1 after `fix.r04` settles
    When the engine decides loop round 4
    Then `loop_decided` reads `capped`
    And every step after the loop is recorded `skipped`
    And the run finishes `failed`, and the exit report names the loop, the decision and the trail

  @flow
  Scenario: A worse number counts as no improvement
    Given the best progress number so far is 9
    When the progress command prints 12 after a loop round
    Then `loop_decided` counts that loop round toward the stall, and its best number stays 9

  @flow
  Scenario: A progress command that prints no number stops the run
    Given the last line of the progress command's output reads "9 failing"
    When the engine decides a loop round
    Then `loop_decided` reads `error` and quotes that line
    And the run finishes `failed`

  @flow
  Scenario: A check command that runs past its time limit stops the run
    Given the stop command runs longer than the loop's `check_timeout_s`
    When the engine decides a loop round
    Then the engine ends the command's process tree
    And `loop_decided` reads `error` with the reason "stop command timed out"
    And the run finishes `failed`

  @flow
  Scenario: A loop round that fails its own gate ends the run as any failed phase does
    Given the phase `fix` has `on_step_failure="abort"`
    And `fixer.r02` failed its gate on every attempt its retry policy allows
    When `fix.r02` settles
    Then the engine runs neither check command and writes no `loop_decided` event for loop round 2
    And the run finishes `failed`, as it does for any aborted phase
