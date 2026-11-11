# Example: missed-meal and problem alerts

The feeder runs its schedule by itself, so Home Assistant isn't told when a meal
is due. This automation checks each feeder 10 minutes after every meal. If the
feeder's *Portions dispensed today* counter hasn't changed in the last 20
minutes, it sends a phone notification. It also alerts when a feeder's
*Problem* sensor has been on for 2 minutes.

**What it can't catch:** a feeder that turns its motor but drops no food (empty
hopper, food stuck above the rotor, not primed). The feeder counts that as
dispensed. Check the bowls now and then.

## Before you paste it

Change these to match your setup:

- **`meal_checks_utc`**: each meal time **in UTC**, plus 10 minutes. Use the
  *meals on feeder* times from the action's response. Example: meals at
  12:10, 18:00 and 23:00 UTC → checks at 12:20, 18:10 and 23:10.
- **`feeders`**: each feeder's name, and the entity ID of its
  *Portions dispensed today* sensor.
- The two `binary_sensor` *Problem* entities.
- The `notify.mobile_app_your_phone` action.

Create a new automation, open **⋮ → Edit in YAML**, and paste:

```yaml
alias: Pet feeder missed meal or problem
description: >-
  Ten minutes after each scheduled meal, alerts if a feeder's portion
  counter didn't change. Also alerts when a feeder reports a problem.
mode: queued
variables:
  meal_checks_utc: ["12:20", "18:10", "23:10"]
  feeders:
    Feeder 1: sensor.pet_feeder_1_portions_dispensed_today
    Feeder 2: sensor.pet_feeder_2_portions_dispensed_today
triggers:
  # Home Assistant's time trigger only knows local time, but the meals are
  # fixed in UTC. This template is true for one minute at each check time.
  - trigger: template
    value_template: >-
      {{ utcnow().strftime('%H:%M') in ['12:20', '18:10', '23:10'] }}
    id: meal_check
  - trigger: state
    entity_id:
      - binary_sensor.pet_feeder_1_problem
      - binary_sensor.pet_feeder_2_problem
    to: "on"
    for:
      minutes: 2
    id: problem
actions:
  - choose:
      - conditions:
          - condition: trigger
            id: meal_check
        sequence:
          - variables:
              missed: >-
                {% set ns = namespace(missed=[]) %}
                {% for name, entity in feeders.items() %}
                  {% if not has_value(entity)
                        or (now() - states[entity].last_changed).total_seconds() > 1200 %}
                    {% set ns.missed = ns.missed + [name] %}
                  {% endif %}
                {% endfor %}
                {{ ns.missed }}
          - condition: template
            value_template: "{{ missed | count > 0 }}"
          - action: notify.mobile_app_your_phone
            data:
              title: Missed meal
              message: >-
                {{ missed | join(' and ') }} didn't dispense the
                {{ (now() - timedelta(minutes=10)).strftime('%-I:%M %p') }} meal.
                Check for a jam or an empty hopper.
      - conditions:
          - condition: trigger
            id: problem
        sequence:
          - action: notify.mobile_app_your_phone
            data:
              title: Feeder problem
              message: >-
                {{ state_attr(trigger.entity_id, 'friendly_name') }} is on.
                Check for a jam or an empty hopper.
```

The trigger repeats the check times instead of reading `meal_checks_utc`,
because triggers are set up before variables exist. Keep the two lists the
same.

## Why the counter check works

*Portions dispensed today* changes every time the feeder dispenses, so its
`last_changed` time is roughly the time of the most recent dispense. Two cases
can hide a missed meal:

- **A hand feed shortly before the meal.** If you press Feed within 20 minutes
  of a check, the counter changed then, so the check passes.
- **A meal just after midnight UTC.** The counter restarts at midnight UTC. If
  that restart shows up in Home Assistant as a change, a meal within 20 minutes
  after it could look dispensed.
