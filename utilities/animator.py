""" Our Animator controller for our RGB display """
from time import sleep
import sys, os
import signal
import logging

DELAY_DEFAULT = 0.01
animator_logger = logging.getLogger("DisplayDriver")

def sigterm_handler(signum, frame):
    # this module will steal signals from our main thread, so we cascade our exit starting from here
    signal.signal(signum, signal.SIG_IGN) # ignore additional signals
    os.write(sys.stdout.fileno(), b"\nDisplay Driver: Exit signal received, shutting down now.\n")
    animator_logger.info("Exit signal received, shutting down now.")
    raise ImportError # hacky
    """ We don't use SystemExit because we will need to try-except it, and the main thread
    will catch the same signal from the main system when we call for external termination or a KeyboardInterrupt,
    which depends on how the main script was initiated. It will cause the signal handler to be called twice,
    which is undesirable. """
    # sys.exit(0) # main thread needs to try-except this or else we just quit without our thread cleanup

class Animator(object):
    class KeyFrame(object):
        @staticmethod
        def add(divisor, offset=0):
            def wrapper(func):
                func.properties = {"divisor": divisor, "offset": offset, "count": 0}
                return func

            return wrapper

    def __init__(self):
        self.keyframes = []
        self.frame = 0
        self._delay = DELAY_DEFAULT
        self._reset_scene = True

        self._register_keyframes()
        
        super().__init__()

        # break out of this loop if the system calls for our termination
        signal.signal(signal.SIGINT, sigterm_handler)
        signal.signal(signal.SIGTERM, sigterm_handler)

    def _register_keyframes(self):
        # Some introspection to setup keyframes
        for methodname in dir(self):
            method = getattr(self, methodname)
            if hasattr(method, "properties"):
                self.keyframes.append(method)

    def reset_scene(self):
        for keyframe in self.keyframes:
            if keyframe.properties["divisor"] == 0:
                keyframe()

    def play(self):
        animator_logger.info("Display started!")
        print("Display Driver: Display started!\n", flush=True)
        try:
            while True:
                for keyframe in self.keyframes:
                    # If divisor == 0 then only run once on first loop
                    if self.frame == 0:
                        if keyframe.properties["divisor"] == 0:
                            keyframe()

                    # Otherwise perform normal operation
                    if (
                        self.frame > 0
                        and keyframe.properties["divisor"]
                        and not (
                            (self.frame - keyframe.properties["offset"])
                            % keyframe.properties["divisor"]
                        )
                    ):
                        if keyframe(keyframe.properties["count"]):
                            keyframe.properties["count"] = 0
                        else:
                            keyframe.properties["count"] += 1

                self._reset_scene = False
                self.frame += 1
                sleep(self._delay)
                
        except (KeyboardInterrupt, SystemExit):
            print("Screen animator exiting...")
            return

    @property
    def delay(self):
        return self._delay

    @delay.setter
    def delay(self, value):
        self._delay = value


if __name__ == "__main__":

    class Test(Animator):
        @Animator.KeyFrame.add(5, 1)
        def method1(self, frame):
            print(f"method1 {frame}")

        @Animator.KeyFrame.add(1, 1)
        def method2(self, frame):
            print(f"method2 {frame}")

    myclass = Test(1)
    myclass.run()

    while 1:
        sleep(5)
