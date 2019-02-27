#!/usr/bin/env python2.7
import rospy
from humanoid_league_msgs.msg import LineInformationInImage, ObstaclesInImage, BallsInImage
from geometry_msgs.msg import Point
from sensor_msgs.msg import Image
import numpy as np
from cv_bridge import CvBridge
import cv2
import yaml
import os
import signal


class Evaluation(object):

    def __init__(self):
        self.received_message = False  # boolean signaling whether a message of the type was received
        self.pixel_mask_rates = None
        self.duration = None


class ImageMeasurement(object):
    def __init__(self, image_data, eval_classes):
        self.evaluations = dict()
        self.image_data = image_data
        for eval_class in eval_classes:
            self.evaluations[eval_class] = Evaluation()

    def serialize(self):
        return {
            'evaluations': {eval_class: vars(self.evaluations[eval_class]) for eval_class in self.evaluations.keys()},
            'image_data': self.image_data
        }

    def get_max_duration(self):
        # returns the maximal duration a measurement in the image took
        max_duration = None
        for eval in self.evaluations.values():
            if eval.duration is not None and eval.duration > max_duration:
                max_duration = eval.duration
        return max_duration


class Evaluator(object):
    def __init__(self):
        rospy.init_node("vision_evaluator")


        self._evaluated_classes = list()

        self._ball_sub = None
        if rospy.get_param("listen_balls", False):
            rospy.loginfo('listening for balls in image...')
            self._evaluated_classes.append('ball')
            self._ball_sub = rospy.Subscriber(rospy.get_param("balls_topic", "balls_in_image"),
                 BallsInImage,
                 self._balls_callback(),
                 queue_size=1,
                 tcp_nodelay=True)

        self._line_sub = None
        if rospy.get_param("listen_lines", False):
            rospy.loginfo('listening for lines in image...')
            self._evaluated_classes.append('line')
            self._line_sub = rospy.Subscriber(rospy.get_param("lines_topic", "lines_in_image"),
                 LineInformationInImage,
                 self._lines_callback(),
                 queue_size=1,
                 tcp_nodelay=True)

        self._obstacle_sub = None
        if rospy.get_param("listen_obstacle", False):
            rospy.loginfo('listening for obstacles in image...')
            self._evaluated_classes.append('obstacle')
            self._evaluated_classes.append('goalpost')
            self._evaluated_classes.append('robot')
            self._line_sub = rospy.Subscriber(rospy.get_param("obstacles_topic", "obstacles_in_image"),
                 ObstaclesInImage,
                 self._obstacles_callback(),
                 queue_size=1,
                 tcp_nodelay=True)

        self._image_pub = rospy.Publisher('image_raw', Image, queue_size=1)

        self._image_path = '~/images'

        self._line_thickness = 3


        # read label YAML file
        self._label_filename = rospy.get_param('label_file_name')
        rospy.loginfo('Reading label-file \"{}\"...'.format(self._label_filename))
        self._images = self._read_labels(self._label_filename)
        rospy.loginfo('Done reading label-file.')
        rospy.loginfo('Validating labels of {} images...'.format(len(self._images)))
        self._images = self._analyze_labels(self._images)
        rospy.loginfo('Labels of {} images are valid'.format(len(self._images)))

        # initialize resend timer
        self._resend_timer = rospy.Timer(rospy.Duration(2), self._resend_callback) # 2 second timer TODO: make this a variable

        self.bridge = CvBridge()

        self._send_image_counter = 0  # represents the image index of the image to be sent in the list defined by the label yaml file
        self._current_image_counter = 0  # represents the current image index in the list defined by the label yaml file
        self._image_count = len(self._images)  # number of images (important for loop stuff)
        self._image_size = None  # tuple (height, width)

        self._measurements = dict()

        # Stop-Stuff
        self._stop = False  # stop flag to handle kills
        signal.signal(signal.SIGINT, self._kill_callback())
        signal.signal(signal.SIGTERM, self._kill_callback())

        rospy.spin()

    def _kill_callback(self):
        # the rest of the process is handled in the send_image method
        self._stop = True

    def _resend_callback(self, event):
        self._send_image(self._get_send_image_name())
        pass

    def _get_send_image_name(self):
        return self._images[self._send_image_counter]['name']

    def _get_current_labels(self):
        return self._images[self._current_image_counter]['annotations']

    def _update_image_counter(self, seq):
        # updates the image counter to publish a new image when necessary
        # (it was not updated already by an other callback)
        # TODO: do loop stuff here!
        if self._send_image_counter <= seq:
            self._send_image_counter += 1

    def _send_image(self, name=None):
        if self._stop:
            # stop timer
            self._resend_timer.shutdown()
            # write measurements to file
            self._write_measurements_to_file()
            # do nothing more
            return

        if name is None:
            name = self._get_send_image_name()
        imgpath = os.path.join(self._image_path, name)
        image = cv2.imread(imgpath)
        if image is None:
            rospy.logwarn('Could not open image {} at path {}'.format(name, self._image_path))
            return

        if self._image_size is None:
            self._image_size = image.shape[:-1]

        msg = self.bridge.cv2_to_imgmsg(image)
        msg.header.stamp = rospy.get_rostime()
        msg.header.seq = self._send_image_counter
        self._image_pub.publish(msg)
        self._current_image_counter = self._send_image_counter  # update the current image counter to the new current image

        # set up evaluation element in measurements list
        self._measurements[self._send_image_counter] = ImageMeasurement(self._images[self._send_image_counter], self._evaluated_classes)

    def _read_labels(self, filename):
        # reads the labels YAML file and returns a list of image names with their labels
        filepath = os.path.join(self._image_path, filename)
        images = None
        with open(filepath, 'r') as stream:
            try:
                images = yaml.load(stream)['labels']
            except yaml.YAMLError as exc:
                rospy.logerr(exc)
        return images

    def _get_image_measurement(self, image_sequence):
        if image_sequence not in self._measurements.keys():
            rospy.logerr('got an unknown image with seq {}! Is there a ROS-bag running? Stop it please!'.format(image_sequence))
            return
        return self._measurements[image_sequence]

    def _balls_callback(self, msg):
        measurement = self._get_image_measurement(msg.header.seq).evaluations['ball']
        # mark as received
        measurement.received_message = True
        # measure duration of processing
        measurement.duration = self._measure_timing(msg.header)
        # match masks
        measurement.pixel_mask_rates = self._match_masks(
            self._generate_circle_mask_from_vectors(
                Evaluator._extract_vectors_from_annotations(
                    self._images[msg.header.seq]['annotations'],
                    typename='ball'
                )),
            self._generate_ball_mask_from_msg(msg))

        if self._recieved_all_messages_for_image(msg.header.seq):
            self._send_image()

    def _obstacles_callback(self, msg):
        # getting the measurement which is set here
        measurement = self._get_image_measurement(msg.header.seq).evaluations['obstacle']
        # mark as received
        measurement.received_message = True
        # measure duration of processing
        measurement.duration = self._measure_timing(msg.header)
        # match masks
        measurement.pixel_mask_rates = self._match_masks(
            self._generate_rectangle_mask_from_vectors(
                Evaluator._extract_vectors_from_annotations(
                    self._images[msg.header.seq]['annotations'],
                    typename='obstacle'
                )),
            self._generate_obstacle_mask_from_msg(msg))

        if self._recieved_all_messages_for_image(msg.header.seq):
            self._send_image()

    def _goalpost_callback(self, msg):
        # getting the measurement which is set here
        measurement = self._get_image_measurement(msg.header.seq).evaluations['goalpost']
        # mark as received
        measurement.received_message = True
        # measure duration of processing
        measurement.duration = self._measure_timing(msg.header)
        # match masks
        measurement.pixel_mask_rates = self._match_masks(
            self._generate_rectangle_mask_from_vectors(
                Evaluator._extract_vectors_from_annotations(
                    self._images[msg.header.seq]['annotations'],
                    typename='goalpost'
                )),
            self._generate_obstacle_mask_from_msg(msg))

        if self._recieved_all_messages_for_image(msg.header.seq):
            self._send_image()

    def _lines_callback(self, msg):
        # getting the measurement which is set here
        measurement = self._get_image_measurement(msg.header.seq).evaluations['line']
        # mark as received
        measurement.received_message = True
        # measure duration of processing
        measurement.duration = self._measure_timing(msg.header)
        # generating and matching masks
        measurement.pixel_mask_rates = self._match_masks(
            self._generate_line_mask_from_vectors(
                Evaluator._extract_vectors_from_annotations(
                    self._images[msg.header.seq]['annotations'],
                    typename='line'
                )),
            self._generate_line_mask_from_msg(msg))

        if self._recieved_all_messages_for_image(msg.header.seq):
            self._send_image()

    def _measure_timing(self, header):
        # calculating the time the processing took
        return rospy.get_rostime() - header.stamp

    def _generate_polygon_mask_from_vectors(self, vectors):
        mask = np.zeros(self._image_size)

        for vector in vectors:
            cv2.fillConvexPoly(mask, vector, 1.0)
        return mask

    def _generate_rectangle_mask_from_vectors(self, vectors):
        mask = np.zeros(self._image_size)

        for vector in vectors:
            cv2.rectangle(mask, vector[0], vector[1], 1.0, thickness=-1)
        return mask

    def _generate_circle_mask_from_vectors(self, vectors):
        mask = np.zeros(self._image_size)

        for vector in vectors:
            center = (vector[0][0] + (vector[1][0] - vector[0][0]) / 2, vector[0][1] + (vector[1][1] - vector[0][1]) / 2)
            radius = ((vector[1][0] - vector[0][0]) / 2 + (vector[1][1] - vector[0][1]) / 2) / 2
            cv2.circle(mask, center, radius, 1.0, thickness=-1)
        return mask

    def _generate_line_mask_from_vectors(self, vectors):
        mask = np.zeros(self._image_size)
        for vector in vectors:
            cv2.line(mask, vector[0], vector[1], 1.0, thickness=self._line_thickness)
        return mask

    def _generate_ball_mask_from_msg(self, msg):
        mask = np.zeros(self._image_size)
        for ball in msg.candidates:
            cv2.circle(mask, (int(round(ball.center.x)), int(round(ball.center.y))), int(round(ball.diameter/2)), 1.0, thickness=-1)
        return mask

    def _generate_obstacle_mask_from_msg(self, msg):
        vectors = list()
        for obstacle in msg.obstacles:
            vector = ((obstacle.top_left.x, obstacle.top_left.y), (obstacle.top_left.x + obstacle.width, obstacle.top_left.y + obstacle.height))
            vectors.append(vector)
        return self._generate_rectangle_mask_from_vectors(vectors)

    def _generate_line_mask_from_msg(self, msg):
        mask = np.zeros(self._image_size)
        for line in msg.segments:
            cv2.line(mask, (int(round(line.start.x)), int(round(line.start.y))), (int(round(line.end.x)), int(round(line.end.y))), 1.0, thickness=self._line_thickness)
        return mask

    @staticmethod
    def _match_masks(label_mask, detected_mask):
        # WARNING: the mask has to be filled with 0 and 1 es
        # matches the masks onto each other to determine multiple measurements.
        rates = dict()
        rates['tp'] = np.mean((np.bitwise_and(label_mask, detected_mask)))
        rates['tn'] = np.mean(np.bitwise_not(np.bitwise_or(label_mask, detected_mask)))
        rates['fp'] = np.mean(np.bitwise_and(detected_mask, np.bitwise_not(label_mask)))
        rates['fn'] = np.mean(np.bitwise_and(np.bitwise_not(detected_mask), label_mask))
        rates['lp'] = np.mean(label_mask)
        rates['ln'] = 1 - rates['lp']  # because all the other pixels have to be negative
        rates['dp'] = np.mean(detected_mask)
        rates['dn'] = 1 - rates['dp']  # because all the other pixels have to be negative
        return rates

    def _recieved_all_messages_for_image(self, image_seq):
        measurement = self._measurements[image_seq]
        for eval_class in self._evaluated_classes:
            if not measurement.evaluations[eval_class].received_message:
                return False
        return True

    @staticmethod
    def _filter_type(annotations, typename):
        # returns the annotations of type TYPE
        return [annotation for annotation in annotations if annotation['type'] == typename]

    @staticmethod
    def _extract_vectors_from_annotations(annotations, typename=None):
        # returns the vectors of annotations of type TYPE
        if typename:
            return [annotation['vector'] for annotation in annotations if annotation['type'] == typename]
        return [annotation['vector'] for annotation in annotations]

    def _analyze_labels(self, images):
        # analyzes the label file for stuff

        not_in_image_count = dict()
        for eval_class in self._evaluated_classes:
            not_in_image_count[eval_class] = 0

        filtered_images = list()
        for image in images:
            add_image = True  # whether the image is used in the evaluation or not
            in_image = dict()
            found_label = dict()
            for eval_class in self._evaluated_classes:
                found_label[eval_class] = False
                in_image[eval_class] = None

            for annotation in image['annotations']:
                # determine whether the class is evaluated or not
                if annotation['type'] not in self._evaluated_classes:
                    continue  # ignore other classes annotations
                # annotation type is in evaluated classes
                found_label[annotation['type']] = True
                if in_image[annotation['type']] == True:
                    if not annotation['in']:  # contradiction!
                        rospy.logwarn('Found contradicting labels of type {} in image \"{}\"! The image will be removed!'.format(annotation['type'], image['name']))
                        add_image = False
                        break
                elif in_image[annotation['type']]  == False:
                    if annotation['in']:  # contradiction!
                        rospy.logwarn('Found contradicting labels of type {} in image \"{}\"! The image will be removed!'.format(annotation['type'], image['name']))
                        add_image = False
                        break
                else:  # it is None and therefor not set yet
                    in_image[annotation['type']] = annotation['in']

            # increase the counters when no label was found for a type
            for eval_class in self._evaluated_classes:
                if not found_label[eval_class]:
                    not_in_image_count[eval_class] += 1
            if add_image:
                filtered_images.append(image)
        return filtered_images

    def _write_measurements_to_file(self):
        serialized_measurements = [measurement.serialize() for measurement in self._measurements]
        rospy.loginfo('Writing {} measurements to file...'.format(len(serialized_measurements)))
        filepath = 'data.yaml'  # TODO: this properly
        with open(filepath, 'w') as outfile:
            yaml.dump(serialized_measurements, outfile)  # , default_flow_style=False)


if __name__ == "__main__":
    Evaluator()
