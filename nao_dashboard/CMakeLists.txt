cmake_minimum_required(VERSION 2.8)
project(nao_dashboard)

find_package(catkin)

find_package(catkin REQUIRED)
catkin_package(DEPENDS 
               LIBRARIES nao_diagnostic_analyzers
)

catkin_python_setup()

add_library(nao_diagnostic_analyzers src/NaoJointsAnalyzer.cpp)
install(TARGETS nao_diagnostic_analyzers DESTINATION ${CATKIN_PACKAGE_LIB_DESTINATION})

install(DIRECTORY config icons launch DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION})
install(FILES nao_analyzer_plugins.xml plugin.xml DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION})
install(PROGRAMS scripts/nao_dashboard DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION})
