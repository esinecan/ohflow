Feature: Working in a loop round
  As an agent in a loop round, I start from the work and the numbers of the loop rounds before
  mine, so that I spend my loop round on what is still left.

  @flow
  Scenario: My loop round starts where the last one ended
    Given `fixer.r02` committed `a1b2c3d` in the loop's worktree
    When my attempt in `fixer.r03` starts
    Then the HEAD of my worktree is `a1b2c3d`

  @brief
  Scenario: My position block holds the state of the loop
    Given the progress trail of the loop `green` reads 14, 9 and 7
    When my attempt in `fixer.r03` starts
    Then my position block has a section "Loop" that names loop round 3 of at most 4, the stop command, and the progress command with its goal
    And the section lists the trail 14, 9 and 7
    And it quotes the last 40 lines of the stop command's output after loop round 2
    And it states that the engine runs the stop command after my loop round, so my final message does not end the loop
    And the hand-try's run notes record whether my commits worked on a failure that the quoted output names

  @brief
  Scenario: I receive the handover of the loop round before mine
    Given the agent of `fixer.r02` wrote its handover
    When my attempt in `fixer.r03` starts
    Then my position block holds that handover under "Handed to you"
    And the hand-try's run notes record whether I repeated an approach that the handover says failed

  @gate:repetition
  Scenario: A change to a check file fails my gate
    Given the loop `green` has `check_paths=("checks/**",)`
    When I commit a change to `checks/failing.sh` in my loop round
    Then my attempt fails the gate check `paths_untouched`, which names `checks/failing.sh`
    And the engine runs neither check command after my attempt
