#! /usr/bin/env python2


from bitbots_vision.vision_modules import lines, horizon, color, debug, live_classifier, classifier, ball, \
    lines2, fcnn_handler, live_fcnn_03, dummy_ballfinder, obstacle, evaluator
from humanoid_league_msgs.msg import BallInImage, BallsInImage, LineInformationInImage, LineSegmentInImage, ObstaclesInImage, ObstacleInImage, ImageWithRegionOfInterest, HorizonInImage
from sensor_msgs.msg import Image
from geometry_msgs.msg import Point
from cv_bridge import CvBridge
import rospy
import rospkg
import cv2
import os
import threading
from dynamic_reconfigure.server import Server
from bitbots_vision.cfg import VisionConfig


class Vision:

    def __init__(self):
        rospack = rospkg.RosPack()
        self.package_path = rospack.get_path('bitbots_vision')

        self.bridge = CvBridge()

        rospy.init_node('bitbots_vision')
        rospy.loginfo('Initializing vision...')

        self.config = {}
        self.debug_image_dings = debug.DebugImage()  # Todo: better variable name
        if self.debug_image_dings:
            self.runtime_evaluator = evaluator.RuntimeEvaluator(None)
        # register config callback and set config
        srv = Server(VisionConfig, self._dynamic_reconfigure_callback)

        rospy.spin()

    def _image_callback(self, img):
        self.handle_image(img)

    def handle_image(self, image_msg):
        # converting the ROS image message to CV2-image
        image = self.bridge.imgmsg_to_cv2(image_msg, 'bgr8')

        # setup detectors
        self.horizon_detector.set_image(image)
        self.obstacle_detector.set_image(image)
        self.line_detector.set_image(image)

        self.runtime_evaluator.set_image()

        if (self.config['vision_ball_classifier'] == 'cascade'):
            self.ball_finder.set_image(image)
            self.ball_detector.set_image(image,
                                         self.horizon_detector.
                                         balls_under_horizon(
                                             self.ball_finder.get_ball_candidates(),
                                             self._ball_candidate_y_offset))

        elif (self.config['vision_ball_classifier'] == 'fcnn'):
            self.ball_detector.set_image(image)

        if self.config['vision_parallelize']:
            self.horizon_detector.compute_all()  # computes stuff which is needed later in the processing
            fcnn_thread = threading.Thread(target=self.ball_detector.compute_top_candidate)
            conventional_thread = threading.Thread(target=self._conventional_precalculation())

            conventional_thread.start()
            fcnn_thread.start()

            conventional_thread.join()
            fcnn_thread.join()
        else:
            self.ball_detector.compute_top_candidate()
            self._conventional_precalculation()

        top_ball_candidate = self.ball_detector.get_top_candidate()

        # create ball msg
        if top_ball_candidate and top_ball_candidate.rating > self._ball_candidate_threshold:
            balls_msg = BallsInImage()
            balls_msg.header.frame_id = image_msg.header.frame_id
            balls_msg.header.stamp = image_msg.header.stamp

            ball_msg = BallInImage()
            ball_msg.center.x = top_ball_candidate.get_center_x()
            ball_msg.center.y = top_ball_candidate.get_center_y()
            ball_msg.diameter = top_ball_candidate.get_diameter()
            ball_msg.confidence = 1

            balls_msg.candidates.append(ball_msg)
            self.debug_printer.info('found a ball! \o/', 'ball')
            self.pub_balls.publish(balls_msg)

        # create obstacle msg
        obstacles_msg = ObstaclesInImage()
        obstacles_msg.header.frame_id = image_msg.header.frame_id
        obstacles_msg.header.stamp = image_msg.header.stamp
        for red_obs in self.obstacle_detector.get_red_obstacles():
            obstacle_msg = ObstacleInImage()
            obstacle_msg.color = ObstacleInImage.ROBOT_MAGENTA
            obstacle_msg.top_left.x = red_obs.get_upper_left_x()
            obstacle_msg.top_left.y = red_obs.get_upper_left_y()
            obstacle_msg.height = int(red_obs.get_height())
            obstacle_msg.width = int(red_obs.get_width())
            obstacle_msg.confidence = 1.0
            obstacle_msg.playerNumber = 42
            obstacles_msg.obstacles.append(obstacle_msg)
        for blue_obs in self.obstacle_detector.get_blue_obstacles():
            obstacle_msg = ObstacleInImage()
            obstacle_msg.color = ObstacleInImage.ROBOT_CYAN
            obstacle_msg.top_left.x = blue_obs.get_upper_left_x()
            obstacle_msg.top_left.y = blue_obs.get_upper_left_y()
            obstacle_msg.height = int(blue_obs.get_height())
            obstacle_msg.width = int(blue_obs.get_width())
            obstacle_msg.confidence = 1.0
            obstacle_msg.playerNumber = 42
            obstacles_msg.obstacles.append(obstacle_msg)
        for other_obs in self.obstacle_detector.get_other_obstacles():
            obstacle_msg = ObstacleInImage()
            obstacle_msg.color = ObstacleInImage.UNDEFINED
            obstacle_msg.top_left.x = other_obs.get_upper_left_x()
            obstacle_msg.top_left.y = other_obs.get_upper_left_y()
            obstacle_msg.height = int(other_obs.get_height())
            obstacle_msg.width = int(other_obs.get_width())
            obstacle_msg.confidence = 1.0
            obstacles_msg.obstacles.append(obstacle_msg)
        self.pub_obstacle.publish(obstacles_msg)

        # create line msg
        line_msg = LineInformationInImage()
        line_msg.header.frame_id = image_msg.header.frame_id
        line_msg.header.stamp = image_msg.header.stamp
        for lp in self.line_detector.get_linepoints():
            ls = LineSegmentInImage()
            ls.start.x = lp[0]
            ls.start.y = lp[1]
            ls.end = ls.start
            line_msg.segments.append(ls)
        self.pub_lines.publish(line_msg)

        horizon_msg = HorizonInImage()
        horizon_msg.header = image_msg.header
        for point in self.horizon_detector.get_horizon_points():
            horizon_msg.points.append(Point(point[0], point[1], 0))


        if self.ball_fcnn_publish_output and self.config['vision_ball_classifier'] == 'fcnn':
            fcnn_image_msg = self.ball_detector.get_cropped_msg()
            fcnn_image_msg.header.stamp = image_msg.header.stamp
            self.pub_ball_fcnn.publish(self.ball_detector.get_cropped_msg())

        # do debug stuff
        if self.debug:
            self.debug_image_dings.set_image(image)
            self.debug_image_dings.draw_obstacle_candidates(
                self.obstacle_detector.get_candidates(),
                (0, 0, 0),
                thickness=3
            )
            self.debug_image_dings.draw_obstacle_candidates(
                self.obstacle_detector.get_red_obstacles(),
                (0, 0, 255),
                thickness=3
            )
            self.debug_image_dings.draw_obstacle_candidates(
                self.obstacle_detector.get_blue_obstacles(),
                (255, 0, 0),
                thickness=3
            )
            self.debug_image_dings.draw_obstacle_candidates(
                self.obstacle_detector.get_white_obstacles(),
                (255, 255, 255),
                thickness=3
            )
            self.debug_image_dings.draw_horizon(
                self.horizon_detector.get_horizon_points(),
                (0, 0, 255))
            self.debug_image_dings.draw_ball_candidates(
                self.ball_detector.get_candidates(),
                (0, 0, 255))
            self.debug_image_dings.draw_ball_candidates(
                self.horizon_detector.balls_under_horizon(
                    self.ball_detector.get_candidates(),
                    self._ball_candidate_y_offset),
                (0, 255, 255))
            # draw top candidate in
            self.debug_image_dings.draw_ball_candidates([top_ball_candidate],
                                                        (0, 255, 0))
            # draw linepoints in black
            self.debug_image_dings.draw_points(
                self.line_detector.get_linepoints(),
                (0, 0, 255))
            # debug_image_dings.draw_line_segments(line_detector.get_linesegments(), (180, 105, 255))
            if self.debug_image:
                self.debug_image_dings.imshow()
            if self.debug_image_msg:
                self.pub_debug_image.publish(self.bridge.cv2_to_imgmsg(self.debug_image_dings.get_image(), 'bgr8'))

    def _conventional_precalculation(self):
        self.obstacle_detector.compute_all_obstacles()
        self.line_detector.compute_linepoints()

    def _dynamic_reconfigure_callback(self, config, level):

        self.debug_printer = debug.DebugPrinter(
            debug_classes=debug.DebugPrinter.generate_debug_class_list_from_string(
                config['vision_debug_printer_classes']))
        self.runtime_evaluator = evaluator.RuntimeEvaluator(self.debug_printer)

        self._ball_candidate_threshold = config['vision_ball_candidate_rating_threshold']
        self._ball_candidate_y_offset = config['vision_ball_candidate_horizon_y_offset']

        self.debug_image = config['vision_debug_image']
        self.debug_image_msg = config['vision_debug_image_msg']
        self.debug = self.debug_image or self.debug_image_msg
        if self.debug:
            rospy.logwarn('Debug images are enabled')
        else:
            rospy.loginfo('Debug images are disabled')
        self.ball_fcnn_publish_output = config['ball_fcnn_publish_output']
        if self.ball_fcnn_publish_output:
            rospy.logwarn('ball FCNN output publishing is enabled')
        else:
            rospy.logwarn('ball FCNN output publishing is disabled')

        if config['vision_ball_classifier'] == 'dummy':
            self.ball_detector = dummy_ballfinder.DummyClassifier(None, None, None)
        # color config
        self.white_color_detector = color.HsvSpaceColorDetector(
            [config['white_color_detector_lower_values_h'], config['white_color_detector_lower_values_s'],
             config['white_color_detector_lower_values_v']],
            [config['white_color_detector_upper_values_h'], config['white_color_detector_upper_values_s'],
             config['white_color_detector_upper_values_v']], self.debug_printer)

        self.red_color_detector = color.HsvSpaceColorDetector(
            [config['red_color_detector_lower_values_h'], config['red_color_detector_lower_values_s'],
             config['red_color_detector_lower_values_v']],
            [config['red_color_detector_upper_values_h'], config['red_color_detector_upper_values_s'],
             config['red_color_detector_upper_values_v']], self.debug_printer)

        self.blue_color_detector = color.HsvSpaceColorDetector(
            [config['blue_color_detector_lower_values_h'], config['blue_color_detector_lower_values_s'],
             config['blue_color_detector_lower_values_v']],
            [config['blue_color_detector_upper_values_h'], config['blue_color_detector_upper_values_s'],
             config['blue_color_detector_upper_values_v']], self.debug_printer)

        self.field_color_detector = color.PixelListColorDetector(
            self.package_path +
            config['field_color_detector_path'],
            self.debug_printer)

        self.horizon_detector = horizon.HorizonDetector(
            self.field_color_detector,
            config,
            self.debug_printer)

        self.line_detector = lines.LineDetector(self.white_color_detector,
                                                self.field_color_detector,
                                                self.horizon_detector,
                                                config,
                                                self.debug_printer)

        self.obstacle_detector = obstacle.ObstacleDetector(
            self.red_color_detector,
            self.blue_color_detector,
            self.white_color_detector,
            self.horizon_detector,
            self.runtime_evaluator,
            config,
            self.debug_printer
        )

        # load cascade
        if config['vision_ball_classifier'] == 'cascade':
            self.cascade_path = self.package_path + config['cascade_classifier_path']
            if 'cascade_classifier_path' not in self.config or \
                    self.config['cascade_classifier_path'] != config['cascade_classifier_path'] or \
                    self.config['vision_ball_classifier'] != config['vision_ball_classifier']:
                if os.path.exists(self.cascade_path):
                    self.cascade = cv2.CascadeClassifier(self.cascade_path)
                else:
                    rospy.logerr(
                        'AAAAHHHH! The specified cascade config file doesn\'t exist!')
            if 'classifier_model_path' not in self.config or \
                    self.config['classifier_model_path'] != config['classifier_model_path'] or \
                    self.config['vision_ball_classifier'] != config['vision_ball_classifier']:
                self.ball_classifier = live_classifier.LiveClassifier(
                    self.package_path + config['classifier_model_path'])
                rospy.logwarn(config['vision_ball_classifier'] + " vision is running now")
            self.ball_detector = classifier.ClassifierHandler(self.ball_classifier, self.debug_printer)

            self.ball_finder = ball.BallFinder(self.cascade, config, self.debug_printer)


        # set up ball config for fcnn
        # these config params have domain-specific names which could be problematic for fcnn handlers handling e.g. goal candidates
        # this enables 2 fcnns with different configs.
        self.ball_fcnn_config = {
            'debug': config['ball_fcnn_debug'] and self.debug_image,
            'threshold': config['ball_fcnn_threshold'],
            'expand_stepsize': config['ball_fcnn_expand_stepsize'],
            'pointcloud_stepsize': config['ball_fcnn_pointcloud_stepsize'],
            'shuffle_candidate_list': config['ball_fcnn_shuffle_candidate_list'],
            'min_candidate_diameter': config['ball_fcnn_min_ball_diameter'],
            'max_candidate_diameter': config['ball_fcnn_max_ball_diameter'],
            'candidate_refinement_iteration_count': config['ball_fcnn_candidate_refinement_iteration_count'],
            'publish_horizon_offset': config['ball_fcnn_publish_horizon_offset'],
        }

        # load fcnn
        if config['vision_ball_classifier'] == 'fcnn':
            if 'ball_fcnn_model_path' not in self.config or \
                    self.config['ball_fcnn_model_path'] != config['ball_fcnn_model_path'] or \
                    self.config['vision_ball_classifier'] != config['vision_ball_classifier']:
                ball_fcnn_path = self.package_path + config['ball_fcnn_model_path']
                if not os.path.exists(ball_fcnn_path):
                    rospy.logerr('AAAAHHHH! The specified fcnn model file doesn\'t exist!')
                self.ball_fcnn = live_fcnn_03.FCNN03(ball_fcnn_path, self.debug_printer)
                rospy.logwarn(config['vision_ball_classifier'] + " vision is running now")
            self.ball_detector = fcnn_handler.FcnnHandler(self.ball_fcnn,
                                                          self.horizon_detector,
                                                          self.ball_fcnn_config,
                                                          self.debug_printer)

        # subscribers
        if 'ROS_img_msg_topic' not in self.config or \
                self.config['ROS_img_msg_topic'] != config['ROS_img_msg_topic']:
            if hasattr(self, 'image_sub'):
                self.image_sub.unregister()
            self.image_sub = rospy.Subscriber(config['ROS_img_msg_topic'],
                                              Image,
                                              self._image_callback,
                                              queue_size=config['ROS_img_queue_size'],
                                              tcp_nodelay=True,
                                              buff_size=60000000)
            # https://github.com/ros/ros_comm/issues/536

        # publishers
        if 'ROS_ball_msg_topic' not in self.config or \
                self.config['ROS_ball_msg_topic'] != config['ROS_ball_msg_topic']:
            if hasattr(self, 'pub_balls'):
                self.pub_balls.unregister()
            self.pub_balls = rospy.Publisher(
                config['ROS_ball_msg_topic'],
                BallsInImage,
                queue_size=1)

        if 'ROS_line_msg_topic' not in self.config or \
                self.config['ROS_line_msg_topic'] != config['ROS_line_msg_topic']:
            if hasattr(self, 'pub_lines'):
                self.pub_lines.unregister()
            self.pub_lines = rospy.Publisher(
                config['ROS_line_msg_topic'],
                LineInformationInImage,
                queue_size=5)

        if 'ROS_obstacle_msg_topic' not in self.config or \
                self.config['ROS_obstacle_msg_topic'] != config['ROS_obstacle_msg_topic']:
            if hasattr(self, 'pub_obstacle'):
                self.pub_obstacle.unregister()
            self.pub_obstacle = rospy.Publisher(
                config['ROS_obstacle_msg_topic'],
                ObstaclesInImage,
                queue_size=3)

        if 'ROS_fcnn_img_msg_topic' not in self.config or \
                self.config['ROS_fcnn_img_msg_topic'] != config['ROS_fcnn_img_msg_topic']:
            if hasattr(self, 'pub_ball_fcnn'):
                self.pub_ball_fcnn.unregister()
            self.pub_ball_fcnn = rospy.Publisher(
                config['ROS_fcnn_img_msg_topic'],
                ImageWithRegionOfInterest,
                queue_size=1)

        self.pub_debug_image = rospy.Publisher(
            'debug_image',
            Image,
            queue_size=1,
        )

        self.config = config

        return config

if __name__ == '__main__':
    Vision()
