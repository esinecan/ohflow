Feature: Declaring a loop
  As the orchestrator agent, I declare a loop in a workflow module, and `ohflow validate` refuses
  every loop that could run without an end, so that a run never spends past a cap I set before it
  started.

  @flow
  Scenario: A loop unrolls into numbered loop rounds before the run starts
    Given my workflow module wraps the phase `fix`, whose one step is `fixer`, in `loop("green", stop_cmd="bash checks/green.sh", progress_cmd="bash checks/failing.sh", progress_goal="down", check_paths=("checks/**",), max_rounds=4)`
    When I run `ohflow validate`
    Then the workflow holds the phases `fix.r01` to `fix.r04` with the steps `fixer.r01` to `fixer.r04`
    And `fixer.r02` names `fixer.r01` in `depends_on`, and in `consumes` when `fixer.r01` writes a handover
    And `validate` prints one line for the loop that names at most 4 loop rounds, the stop command, and the progress command with its goal

  @gate:repetition
  Scenario: A loop needs a cap of at least one loop round
    Given my workflow declares the loop `green` with `max_rounds=0`
    When I run `ohflow validate`
    Then it exits 1 with an error that names the loop `green` and `max_rounds`

  @gate:repetition
  Scenario: A loop needs a progress command and a direction
    Given my workflow declares the loop `green` with an empty `progress_cmd`, or with a `progress_goal` other than `down` or `up`
    When I run `ohflow validate`
    Then it exits 1 with an error that names the loop `green` and the field

  @gate:irreversible
  Scenario: A loop is refused in an empirical procedure
    Given my workflow sets `kind="empirical"` and declares a loop
    When I run `ohflow validate`
    Then it exits 1 with an error that says an empirical procedure fixes its procedure up front, and a loop that ends on its own result chooses its stopping point by that result

  @gate:irreversible
  Scenario: A loop needs the workflow to name its objective kind
    Given my workflow declares a loop and leaves `kind` empty
    When I run `ohflow validate`
    Then it exits 1 with an error that asks for `kind`, `delivery` or `empirical`

  @gate:repetition
  Scenario: The check files lie outside every loop round's write scope
    Given the loop `green` has `check_paths=("checks/**",)`
    And the step `fixer` has `write_scope=("src/**", "checks/**")`
    When I run `ohflow validate`
    Then it exits 1 with an error that names the step `fixer` and the glob `checks/**`

  @flow
  Scenario: construct gives each milestone workflow the bundle's kind
    Given `bundle.md` reads `kind: delivery`
    When I run `ohflow construct`
    Then every milestone workflow it writes sets `kind="delivery"`
