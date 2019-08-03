# Custom Queues

To add custom queues for viewers to join, simply set the property `queue_names_list=` in your `bot.properties`.

Example:
```
queue_names_list=icecream,cake
```

To do this on the fly, simply run the following command with the list of desired queues. Note that running this command will reset and remove existing queues.

```
!queueinit <queuename1> <queuename2> ...
```

The list of queues must be comma-delimited. Any number of queues are allowed but users may only join one queue at a time. 

Bot commands:

Commands specific to available queues begin with `!<queuename>`. The queue name `icecream` will be used for the example uses below.

- `!icecream`: if no arguments are passed to this commmand then this will add the viewer to the specified queue. If the viewer already belongs to another queue then they will be alerted and told to leave the other queue if they wish to join the new one.
- `!icecream leave`: allows user to leave the specified queue

Queue commands restricted to only the broadcaster.

- `!icecream next`: Prints the next username in the queue. If there are more usernames in the queue then it will also print who is on deck (or second) in queue. If the queue is empty then a message saying so will be printed instead.
- `!icecream win`: Increments the score of the specified queue and then prints the updated score(s) for the queue(s). 

Other queue-specific commands:

- `!print`: prints all of the usersnames in each available queue. 

> Current queue for icecream: xcornflowerx;  Current queue for cake: xhubflowerx

- `!score`: prints the current score(s) for each available queue.


Additional broadcoaster-only permitted queue command:
- `!queueinit <queuename1> <queuename2>`: resets or initializes the available queues to the specified list.

Usage:
> !queueinit icecream cake

Output:
> Available queue(s) to join: icecream, cake