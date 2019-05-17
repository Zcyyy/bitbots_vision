#include <ros/ros.h>
#include <image_transport/image_transport.h>
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/opencv.hpp>
#include <cv_bridge/cv_bridge.h>
#include <dynamic_reconfigure/server.h>
#include <white_balancer/WhiteBalanceConfig.h>
#include <chrono> 
#include <ctime> 
#include <boost/bind.hpp>


class WhiteBalancer
{
public:
    WhiteBalancer();
    void callbackRC(white_balancer::WhiteBalanceConfig &config, uint32_t level);
private:
    image_transport::Publisher pub;
    const std::map<int, std::vector<int>> kelvin =  {
                                                    { 1000,  { 255,  56,   1 }},
                                                    { 1100,  { 255,  71,   1 }},
                                                    { 1200,  { 255,  83,   1 }},
                                                    { 1300,  { 255,  93,   1 }},
                                                    { 1400,  { 255, 101,   1 }},
                                                    { 1500,  { 255, 109,   1 }},
                                                    { 1600,  { 255, 115,   1 }},
                                                    { 1700,  { 255, 121,   1 }},
                                                    { 1800,  { 255, 126,   1 }},
                                                    { 1900,  { 255, 131,   1 }},
                                                    { 2000,  { 255, 138,  18 }},
                                                    { 2100,  { 255, 142,  33 }},
                                                    { 2200,  { 255, 147,  44 }},
                                                    { 2300,  { 255, 152,  54 }},
                                                    { 2400,  { 255, 157,  63 }},
                                                    { 2500,  { 255, 161,  72 }},
                                                    { 2600,  { 255, 165,  79 }},
                                                    { 2700,  { 255, 169,  87 }},
                                                    { 2800,  { 255, 173,  94 }},
                                                    { 2900,  { 255, 177, 101 }},
                                                    { 3000,  { 255, 180, 107 }},
                                                    { 3100,  { 255, 184, 114 }},
                                                    { 3200,  { 255, 187, 120 }},
                                                    { 3300,  { 255, 190, 126 }},
                                                    { 3400,  { 255, 193, 132 }},
                                                    { 3500,  { 255, 196, 137 }},
                                                    { 3600,  { 255, 199, 143 }},
                                                    { 3700,  { 255, 201, 148 }},
                                                    { 3800,  { 255, 204, 153 }},
                                                    { 3900,  { 255, 206, 159 }},
                                                    { 4000,  { 255, 209, 163 }},
                                                    { 4100,  { 255, 211, 168 }},
                                                    { 4200,  { 255, 213, 173 }},
                                                    { 4300,  { 255, 215, 177 }},
                                                    { 4400,  { 255, 217, 182 }},
                                                    { 4500,  { 255, 219, 186 }},
                                                    { 4600,  { 255, 221, 190 }},
                                                    { 4700,  { 255, 223, 194 }},
                                                    { 4800,  { 255, 225, 198 }},
                                                    { 4900,  { 255, 227, 202 }},
                                                    { 5000,  { 255, 228, 206 }},
                                                    { 5100,  { 255, 230, 210 }},
                                                    { 5200,  { 255, 232, 213 }},
                                                    { 5300,  { 255, 233, 217 }},
                                                    { 5400,  { 255, 235, 220 }},
                                                    { 5500,  { 255, 236, 224 }},
                                                    { 5600,  { 255, 238, 227 }},
                                                    { 5700,  { 255, 239, 230 }},
                                                    { 5800,  { 255, 240, 233 }},
                                                    { 5900,  { 255, 242, 236 }},
                                                    { 6000,  { 255, 243, 239 }},
                                                    { 6100,  { 255, 244, 242 }},
                                                    { 6200,  { 255, 245, 245 }},
                                                    { 6300,  { 255, 246, 247 }},
                                                    { 6400,  { 255, 248, 251 }},
                                                    { 6500,  { 255, 249, 253 }},
                                                    { 6600,  { 254, 249, 255 }},
                                                    { 6700,  { 252, 247, 255 }},
                                                    { 6800,  { 249, 246, 255 }},
                                                    { 6900,  { 247, 245, 255 }},
                                                    { 7000,  { 245, 243, 255 }},
                                                    { 7100,  { 243, 242, 255 }},
                                                    { 7200,  { 240, 241, 255 }},
                                                    { 7300,  { 239, 240, 255 }},
                                                    { 7400,  { 237, 239, 255 }},
                                                    { 7500,  { 235, 238, 255 }},
                                                    { 7600,  { 233, 237, 255 }},
                                                    { 7700,  { 231, 236, 255 }},
                                                    { 7800,  { 230, 235, 255 }},
                                                    { 7900,  { 228, 234, 255 }},
                                                    { 8000,  { 227, 233, 255 }},
                                                    { 8100,  { 225, 232, 255 }},
                                                    { 8200,  { 224, 231, 255 }},
                                                    { 8300,  { 222, 230, 255 }},
                                                    { 8400,  { 221, 230, 255 }},
                                                    { 8500,  { 220, 229, 255 }},
                                                    { 8600,  { 218, 229, 255 }},
                                                    { 8700,  { 217, 227, 255 }},
                                                    { 8800,  { 216, 227, 255 }},
                                                    { 8900,  { 215, 226, 255 }},
                                                    { 9000,  { 214, 225, 255 }},
                                                    { 9100,  { 212, 225, 255 }},
                                                    { 9200,  { 211, 224, 255 }},
                                                    { 9300,  { 210, 223, 255 }},
                                                    { 9400,  { 209, 223, 255 }},
                                                    { 9500,  { 208, 222, 255 }},
                                                    { 9600,  { 207, 221, 255 }},
                                                    { 9700,  { 207, 221, 255 }},
                                                    { 9800,  { 206, 220, 255 }},
                                                    { 9900,  { 205, 220, 255 }},
                                                    { 10000, { 207, 218, 255 }},
                                                    { 10100, { 207, 218, 255 }},
                                                    { 10200, { 206, 217, 255 }},
                                                    { 10300, { 205, 217, 255 }},
                                                    { 10400, { 204, 216, 255 }},
                                                    { 10500, { 204, 216, 255 }},
                                                    { 10600, { 203, 215, 255 }},
                                                    { 10700, { 202, 215, 255 }},
                                                    { 10800, { 202, 214, 255 }},
                                                    { 10900, { 201, 214, 255 }},
                                                    { 11000, { 200, 213, 255 }},
                                                    { 11100, { 200, 213, 255 }},
                                                    { 11200, { 199, 212, 255 }},
                                                    { 11300, { 198, 212, 255 }},
                                                    { 11400, { 198, 212, 255 }},
                                                    { 11500, { 197, 211, 255 }},
                                                    { 11600, { 197, 211, 255 }},
                                                    { 11700, { 197, 210, 255 }},
                                                    { 11800, { 196, 210, 255 }},
                                                    { 11900, { 195, 210, 255 }},
                                                    { 12000, { 195, 209, 255 }}};

    int temp = 1000;
    void imageCallback(const sensor_msgs::ImageConstPtr& msg);
    void set_temp(int temp);
};

WhiteBalancer::WhiteBalancer()
{
    ros::NodeHandle nh;
    image_transport::ImageTransport it(nh);

    dynamic_reconfigure::Server<white_balancer::WhiteBalanceConfig> server;
    dynamic_reconfigure::Server<white_balancer::WhiteBalanceConfig>::CallbackType f;
    f = boost::bind(&WhiteBalancer::callbackRC, this, _1, _2);
    server.setCallback(f);

    WhiteBalancer::pub = it.advertise("/image", 1);
    image_transport::Subscriber sub = it.subscribe("/image_raw", 1, &WhiteBalancer::imageCallback, this);
    ros::spin();
}

void WhiteBalancer::set_temp(int temp)
{
    WhiteBalancer::temp = 100 * ((int) temp / 100);
}

void WhiteBalancer::imageCallback(const sensor_msgs::ImageConstPtr& msg)
{
    // Using time point and system_clock 
    std::chrono::time_point<std::chrono::system_clock> start, end; 
    try
    {
        std::vector <int> white_value = WhiteBalancer::kelvin.at(WhiteBalancer::temp);

        std::vector <float> scalars = {0, 0, 0};

        for (int channel = 0; channel < 3; channel ++)
        {
            scalars[channel] = 255.0/white_value[2 - channel];
        }

        cv::Mat image = cv_bridge::toCvShare(msg, "bgr8")->image;
        start = std::chrono::system_clock::now(); 
        int dim_x = image.cols;
        int dim_y = image.rows;

        for (int row = 0; row < dim_x; row++)
        {
            for (int column = 0; column < dim_y; column++)
            {
                for (int channel = 0; channel < 3; channel++)
                {
                    int color = image.at<cv::Vec3b>(column, row)[channel];
                    int new_value = scalars[channel] * color;
                    int new_value_limeted = 255 ^ ((new_value ^ 255) & -(new_value < 255)); // min(x, 255)
                    image.at<cv::Vec3b>(column, row)[channel] = new_value_limeted;
                }
            }
        } 
        end = std::chrono::system_clock::now();
        sensor_msgs::ImagePtr msg = cv_bridge::CvImage(std_msgs::Header(), "bgr8", image).toImageMsg();
        WhiteBalancer::pub.publish(msg);
        //std::cout << image << std::endl;
    }
    catch (cv_bridge::Exception& e)
    {
        ROS_ERROR("Could not convert from '%s' to 'bgr8'.", msg->encoding.c_str());
    }
    std::chrono::duration<double> elapsed_seconds = end - start;
    std::cout << "elapsed time: " << elapsed_seconds.count() << std::endl; 
}

void WhiteBalancer::callbackRC(white_balancer::WhiteBalanceConfig &config, uint32_t level) {
    WhiteBalancer::set_temp(config.temp);
}
  
int main(int argc, char **argv)
{
    ros::init(argc, argv, "white_balancer");
    WhiteBalancer w;

    return 0;
}
