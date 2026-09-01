""" Our Animator controller for our RGB display.
Originally designed by Colin Waddell for his `its-a-plane-python` (v1) project,
but adapted and extended for FlightGazer. """
from time import sleep, perf_counter
import logging

ANIMATOR_VERSION = '11.8.0'
DELAY_DEFAULT = 0.01
animator_logger = logging.getLogger("DisplayDriver")
animator_logger.debug(f"Loaded in Animator module version \'{ANIMATOR_VERSION}\'")

class Animator(object):
    class KeyFrame(object):
        @staticmethod
        def add(divisor, offset=0):
            def wrapper(func):
                func.properties = {"divisor": divisor, "offset": offset, "count": 0}
                return func
            return wrapper

    def __init__(self, exit_signal):
        self.exit_signal = exit_signal
        self.keyframes = []
        self.frame = 0
        self._delay = DELAY_DEFAULT
        self._reset_scene = True
        # render stats
        self.render_time = [0.0, 0.0] # ms/frame, FPS
        self._frame_times = []
        self._render_counter = 0
        self._polling_window_sec = 1
        self._polling_window_start = 0.

        self._register_keyframes()

        super().__init__()

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
        self._polling_window_start = perf_counter()
        try:
            while not self.exit_signal.is_set():
                frame_timer_start = perf_counter()
                for keyframe in self.keyframes:
                    # If divisor == 0 then only run once on first loop
                    if self.frame == 0 and keyframe.properties["divisor"] == 0:
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

                # do the frame stats
                self._frame_times.append((perf_counter() - frame_timer_start) * 1000)
                self._render_counter += 1
                if (perf_counter() - self._polling_window_start) > self._polling_window_sec:
                    if self._frame_times:
                        self.render_time[0] = round((sum(self._frame_times) / len(self._frame_times)), 3)
                        self.render_time[1] = round(self._render_counter / (perf_counter() - self._polling_window_start), 1)
                        self._render_counter = 0
                        self._frame_times.clear()
                        self._polling_window_start = perf_counter()

                self._reset_scene = False
                self.frame += 1
                sleep(self._delay)

            animator_logger.debug(f"Animator thread shutdown. Rendered {self.frame} frames.")
            return

        except KeyboardInterrupt:
            print("Screen animator exiting...")
            return

        except Exception as e:
            raise e

    @property
    def delay(self):
        return self._delay

    @delay.setter
    def delay(self, value):
        self._delay = value