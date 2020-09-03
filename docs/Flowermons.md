Flowermons

Flowermons is a simple chat game allowing users to catch pokemon. The pokemon caught by each user will be stored across each streaming session 

Catch and store pokemon with Flowermons commands.

Commands:
- !catch: allows user to catch a pokemon
- !flowerdex: allows user to check their current FlowerDex stats
- !leaders: returns the current FlowerDex leaderboards
- !flowermons: points user to this document :)

Broadcaster-specific command:
- !addballs [username] [bits | dollars | balls ] [quantity]

Argument descriptions:
 - username: the twitch username to give additional balls to for catching mons
 - [ bits | dollars | balls ]: specify one of these options to give balls based on bits or dollars donated, or specify a number of balls to give user
 - quantity: the number of bits or amount of dollars donated towards purchasing balls OR the specific number of balls to give the user

Example:

```
!addballs flowerbot bits 1000
```

To enable sub-only mode, set the following property as shown below:

```
flowermons.subs_only_mode=true
```
