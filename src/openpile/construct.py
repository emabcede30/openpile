"""
`Construct` module
==================

The `construct` module is used to construct all objects that 
form the inputs to calculations in openpile. 


These objects include:

- the Pile
- the SoilProfile
  - the Layer
- the Model

**Usage**

>>> from openpile.construct import Pile, SoilProfile, Layer, Model

"""

import math as m
import pandas as pd
import numpy as np
import warnings

import openpile.utils.graphics as graphics

from openpile.materials import PileMaterial
from openpile.core import misc, _model_build
from openpile.soilmodels import LateralModel, AxialModel
from openpile.core.misc import generate_color_string
from openpile.calculate import isplugged

from abc import ABC, abstractmethod, abstractproperty
from typing import List, Dict, Optional, Union
from typing_extensions import Literal, Annotated, Optional
from pydantic import BaseModel, AfterValidator, ConfigDict, Field, model_validator

from pydantic import (
    BaseModel,
    Field,
    root_validator,
    model_validator,
    validator,
    PositiveFloat,
    confloat,
    conlist,
    constr,
)

class AbstractPile(BaseModel, ABC):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra='forbid')

class AbstractLayer(BaseModel, ABC):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra='forbid')

class AbstractSoilProfile(BaseModel, ABC):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra='forbid')

class AbstractModel(BaseModel, ABC):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra='forbid')


class PileSection(BaseModel, ABC):
    """
    A Pile Segment is a section of a pile.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra='forbid')

    @abstractmethod
    def get_top_elevation(self) -> float:
        pass

    @abstractmethod
    def get_bottom_elevation(self) -> float:
        pass

    @abstractmethod
    def get_footprint(self) -> float:
        pass

    @abstractmethod
    def get_length(self) -> float:
        pass

    @abstractmethod
    def get_area(self) -> float:
        pass

    @abstractmethod
    def get_volume(self) -> float:
        return self.area() * self.length()
    
    @abstractmethod
    def get_width(self) -> float:
        pass

    @abstractmethod
    def get_second_moment_of_area(self) -> float:
        pass

class CircularPileSection(PileSection):
    """A circular section of a pile.

    Parameters
    ----------
    top_elevation : float
        the top elevation of the circular section, in meters
    bottom_elevation : float
        the bottom elevation of the circular section, in meters
    diameter : float
        the diameter of the circular section, in meters
    thickness : Optional[float], optional
        the wall thickness of the circular section if the section is hollow, in meters, 
        by default None which means the section is solid.

    """
    top_elevation: float
    bottom_elevation: float
    diameter: Annotated[float,Field(gt=0)]
    thickness: Optional[Annotated[float,Field(gt=0)]] = None


    @model_validator(mode='after')
    def get_proper_thickness(self):
        if self.thickness is None:
            self.thickness = self.diameter / 2
        return self
    
    @model_validator(mode='after')
    def check_elevations(self):
        if self.bottom_elevation >= self.top_elevation:
            raise ValueError(f"Bottom elevation ({self.bottom_elevation}) must be less than top elevation ({self.top_elevation}).")
        return self
    
    def get_top_elevation(self) -> float:
        return self.top_elevation

    def get_bottom_elevation(self) -> float:
        return self.bottom_elevation
    
    def get_length(self) -> float:
        return self.top_elevation - self.bottom_elevation

    def get_area(self) -> float:
        return ( self.diameter**2 - (self.diameter - 2*self.thickness)**2 ) * m.pi / 4
    
    def get_footprint(self) -> float:
        return self.diameter**2 * m.pi / 4

    def get_width(self) -> float:
        return self.diameter
    
    def get_second_moment_of_area(self) -> float:
        return ( self.diameter**4 - (self.diameter - 2*self.thickness)**4 ) * m.pi / 64

    def get_volume(self) -> float:
        return self.get_area() * self.get_length()


class Pile(AbstractPile):
    #: name of the pile
    name: str
    #: There can be as many sections as needed by the user. The length of the listsdictates the number of pile sections.
    pile_sections: List[PileSection]
    #: select the type of material the pile is made of, can be of ('Steel', 'Concrete') or a material created from openpile.materials.PileMaterial.custom()
    material: Union[Literal["Steel", "Concrete"], PileMaterial]
    """
    A class to create the pile.

    Parameters
    ----------
    name : str
        Pile/Structure's name.
    pile_sections : List[CircularPileSection]
        argument that stores the relevant data of each pile segment. numbering of sections is made from uppermost elevation and 0-indexed.
    material : Literal["Steel",]
        material the pile is made of. by default "Steel"


    Example
    -------

    >>> from openpile.construct import Pile, CircularPileSection
    >>> # Create a pile instance with two sections of respectively 10m and 30m length.
    >>> pile = Pile(name = "",
    ...         material='Steel',
    ...         pile_sections=[
    ...             CircularPileSection(
    ...                 top_elevation=0, 
    ...                 bottom_elevation=-10, 
    ...                 diameter=7.5, 
    ...                 thickness=0.07
    ...             ),
    ...             CircularPileSection(
    ...                 top_elevation=-10, 
    ...                 bottom_elevation=-40, 
    ...                 diameter=7.5, 
    ...                 thickness=0.08
    ...             ),
    ...         ]
    ...     )

    One can also create a pile from other constructors such as: create_tubular(), that creates a ciruclar hollow pile of one unique section.

    >>> from openpile.construct import Pile
    >>> pile = Pile.create_tubular(name = "",
    ...         top_elevation = 0,
    ...         bottom_elevation = -40,
    ...         diameter=7.5,
    ...         wt=0.07,
    ...         )
    """

    # check that dict is correctly entered
    @model_validator(mode="after")
    def pile_sections_must_not_overlap(self):
        self.pile_sections = sorted(self.pile_sections, key=lambda x: -x.get_top_elevation())
        for i, segment in enumerate(self.pile_sections):
            if i == 0:
                pass
            else:
                previous_segment = self.pile_sections[i-1]
                if segment.top_elevation != previous_segment.bottom_elevation:
                    raise ValueError(f"Pile sections are not consistent. Pile section No. {i} and No. {i-1} do not connect.")
        return self

    # check that dict is correctly entered
    @model_validator(mode="after")
    def check_materials(self):
        if self.material == "Steel":
            self.material = PileMaterial.steel()
        elif self.material == "Concrete":
            self.material = PileMaterial.concrete()
        return self

    @property
    def top_elevation(self) -> float:
        return self.pile_sections[0].get_top_elevation()

    @property
    def data(self) -> pd.DataFrame:
        # create pile data used by openpile for mesh and calculations.
        # Create top and bottom elevations
        elevation = []
        # add bottom of section i and top of section i+1 (essentially the same values)
        for segment in self.pile_sections:
            elevation.append(segment.get_top_elevation())
            elevation.append(segment.get_bottom_elevation())

        # create sectional properties
        width = [x.get_width() for x in self.pile_sections for x in [x,x]]
        area = [x.get_area() for x in self.pile_sections for x in [x,x]]
        second_moment_of_area = [x.get_second_moment_of_area() for x in self.pile_sections for x in [x,x]]

        if all([isinstance(x,CircularPileSection) for x in self.pile_sections]):
            return pd.DataFrame(
                data={
                    "Elevation [m]": elevation,
                    "Diameter [m]": width,
                    "Wall thickness [m]":[x.thickness for x in self.pile_sections for x in [x,x]],
                    "Area [m2]": area,
                    "I [m4]": second_moment_of_area,
                }
            )
        else:
            return pd.DataFrame(
                data={
                    "Elevation [m]": elevation,
                    "Width [m]": width,
                    "Area [m2]": area,
                    "I [m4]": second_moment_of_area,
                }
            )

    def __str__(self):
        return self.data.to_string()

    @property
    def bottom_elevation(self) -> float:
        """
        Bottom elevation of the pile [m VREF].
        """
        return self.pile_sections[-1].get_bottom_elevation()

    @property
    def length(self) -> float:
        """
        Pile length [m].
        """
        return self.top_elevation - self.bottom_elevation

    @property
    def volume(self) -> float:
        """
        Pile volume [m3].
        """
        return round(sum([x.get_area() * x.get_length() for x in self.pile_sections]), 2)

    @property
    def weight(self) -> float:
        """
        Pile weight [kN].
        """
        return round(self.volume * self.material.unitweight, 2)

    @property
    def G(self) -> float:
        """
        Shear modulus of the pile material [kPa]. Thie value does not vary across and along the pile.
        """
        return self.material.shear_modulus

    @property
    def E(self) -> float:
        """
        Young modulus of the pile material [kPa]. Thie value does not vary across and along the pile.
        """
        return self.material.young

    @property
    def tip_area(self) -> float:
        "Sectional area at the bottom of the pile [m2]"
        return self.pile_sections[-1].get_area()

    @property
    def tip_footprint(self) -> float:
        "footprint area at the bottom of the pile [m2]"
        return self.pile_sections[-1].get_footprint()


    @classmethod
    def create_tubular(
        cls,
        name: str,
        top_elevation: float,
        bottom_elevation: float,
        diameter: float,
        wt: float,
        material: str = "Steel",
    ):
        """A method to simplify the creation of a Pile instance.
        This method creates a circular and hollow pile of constant diameter and wall thickness.

        Parameters
        ----------
        name : str
            Pile/Structure's name.
        top_elevation : float
            top elevation of the pile [m VREF]
        bottom_elevation : float
            bottom elevation of the pile [m VREF]
        diameter : float
            pile diameter [m]
        wt : float
            pile's wall thickness [m]
        material : Literal["Steel",]
            material the pile is made of. by default "Steel"

        Returns
        -------
        openpile.construct.Pile
            a Pile instance.
        """

        obj = cls(
            name=name,
            material=material,
            pile_sections=[
                CircularPileSection(
                    top_elevation=top_elevation,
                    bottom_elevation=bottom_elevation,
                    diameter=diameter,
                    thickness=wt,
                )
            ]
        )
        return obj


    def plot(self, assign=False):
        """Creates a plot of the pile with the properties.

        Parameters
        ----------
        assign : bool, optional
            this parameter can be set to True to return the figure, by default False

        Returns
        -------
        matplotlib.pyplot.figure
            only return the object if assign=True

        Example
        -------

        .. image:: _static/plots/Pile_plot.png
           :width: 70%

        """
        fig = graphics.pile_plot(self)
        return fig if assign else None



class Layer(AbstractLayer):
    """A class to create a layer.

    The Layer stores information on the soil parameters of the layer as well
    as the relevant/representative constitutive model (aka. the soil spring).

    Parameters
    ----------
    name : str
        Name of the layer, use for printout.
    top : float
        top elevation of the layer in [m].
    bottom : float
        bottom elevation of the layer in [m].
    weight : float
        total unit weight in [kN/m3], cannot be lower than 10.
    lateral_model : LateralModel
        Lateral soil model of the layer, by default None.
    axial_model : AxialModel
        Axial soil model of the layer, by default None.
    color : str
        soil layer color in HEX format (e.g. '#000000'), by default None.
        If None, the color is generated randomly.


    Example
    -------

    >>> from openpile.construct import Layer
    >>> from openpile.soilmodels import API_clay
    >>> # Create a layer with increasing values of Su and eps50
    >>> layer1 = Layer(name='Soft Clay',
    ...            top=0,
    ...            bottom=-10,
    ...            weight=19,
    ...            lateral_model=API_clay(Su=[30,35], eps50=[0.01, 0.02], kind='static'),
    ...            )
    >>> # show layer
    >>> print(layer1) # doctest: +NORMALIZE_WHITESPACE
    Name: Soft Clay
    Elevation: (0.0) - (-10.0) m
    Weight: 19.0 kN/m3
    Lateral model:      API clay
        Su = 30.0-35.0 kPa
        eps50 = 0.01-0.02
        static curves
    Axial model: None
    """

    #: name of the layer, use for printout
    name: str
    #: top elevaiton of the layer
    top: float
    #: bottom elevaiton of the layer
    bottom: float
    #: unit weight in kN of the layer
    weight: Annotated[float, Field(gt=10.0)]
    #: Lateral constitutive model of the layer
    lateral_model: Optional[LateralModel] = None
    #: Axial constitutive model of the layer
    axial_model: Optional[AxialModel] = None
    #: Layer's color when plotted
    color: Optional[Annotated[str,Field(min_length=7, max_length=7)]] = None

    def model_post_init(self,*args,**kwargs):
        if self.color is None:
            self.color = generate_color_string("earth")
        return self

    def __str__(self):
        return f"Name: {self.name}\nElevation: ({self.top}) - ({self.bottom}) m\nWeight: {self.weight} kN/m3\nLateral model: {self.lateral_model}\nAxial model: {self.axial_model}"

    @model_validator(mode="after")
    def check_elevations(self):  
        if not self.top > self.bottom:
            print("Bottom elevation is higher than top elevation")
            raise ValueError
        else:
            return self


class SoilProfile(AbstractSoilProfile):
    """
    A class to create the soil profile. A soil profile consist of a ground elevation (or top elevation)
    with one or more layers of soil.

    Additionally, a soil profile can include discrete information at given elevation such as CPT
    (Cone Penetration Test) data. Not Implemented yet!

    Parameters
    ----------
    name : str
        Name of the soil profile, used for printout and plots.
    top_elevation : float
        top elevation of the soil profile in [m VREF].
    water_line : float
        elevation of the water table in [m VREF].
    layers : list[Layer]
        list of layers for the soil profile.
    cpt_data : np.ndarray
        cpt data table with
        1st col: elevation [m],
        2nd col: cone resistance [kPa],
        3rd col: sleeve friction [kPa],
        4th col: pore pressure u2 [kPa].

    Example
    -------
    >>> # import objects
    >>> from openpile.construct import SoilProfile, Layer
    >>> from openpile.soilmodels import API_sand, API_clay
    >>> # Create a two-layer soil profile
    >>> sp = SoilProfile(
    ...     name="BH01",
    ...     top_elevation=0,
    ...     water_line=0,
    ...     layers=[
    ...         Layer(
    ...             name='Layer0',
    ...             top=0,
    ...             bottom=-20,
    ...             weight=18,
    ...             lateral_model= API_sand(phi=30, kind='cyclic')
    ...         ),
    ...         Layer( name='Layer1',
    ...                 top=-20,
    ...                 bottom=-40,
    ...                 weight=19,
    ...                 lateral_model= API_clay(Su=50, eps50=0.01, kind='static'),)
    ...     ]
    ... )
    >>> # Check soil profile content
    >>> print(sp) # doctest: +NORMALIZE_WHITESPACE
    Layer 1
    ------------------------------
    Name: Layer0
    Elevation: (0.0) - (-20.0) m
    Weight: 18.0 kN/m3
    Lateral model: 	API sand
        phi = 30.0°
        cyclic curves
    Axial model: None
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    Layer 2
    ------------------------------
    Name: Layer1
    Elevation: (-20.0) - (-40.0) m
    Weight: 19.0 kN/m3
    Lateral model: 	API clay
        Su = 50.0 kPa
        eps50 = 0.01
        static curves
    Axial model: None
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    """

    #: name of soil profile / borehole / location
    name: str
    #: top of ground elevation with respect to the model reference elevation datum
    top_elevation: float
    #: water elevation (this can refer to sea elevation of water table)
    water_line: float
    #: soil layers to consider in the soil propfile
    layers: List[Layer]
    #: Cone Penetration Test data with folloeing structure:
    #: 1st col: elevation[m],
    #: 2nd col: cone resistance[kPa],
    #: 3rd col: sleeve friction [kPa]
    #: 4th col: pore pressure u2 [kPa]
    #: (the cpt data outside the soil profile boundaries will be ignored)
    cpt_data: Optional[np.ndarray] = None

    @model_validator(mode="after")
    def check_layers_elevations(self): 

        top_elevations = np.array([x.top for x in self.layers], dtype=float)
        bottom_elevations = np.array([x.bottom for x in self.layers], dtype=float)
        idx_sort = np.argsort(top_elevations)

        top_sorted = top_elevations[idx_sort][::-1]
        bottom_sorted = bottom_elevations[idx_sort][::-1]

        # check no overlap
        if top_sorted[0] != self.top_elevation:
            raise ValueError("top_elevation not matching uppermost layer's elevations.")

        for i in range(len(top_sorted) - 1):
            if not m.isclose(top_sorted[i + 1], bottom_sorted[i], abs_tol=0.001):
                raise ValueError("Layers' elevations overlap.")

        return self

    @model_validator(mode="after")
    def check_multipliers_in_lateral_model(self):
        def check_multipliers_callable(multiplier, ground_level, top, bottom, type):
            # if not a float, it must be a callable, then we check for Real Positive float
            if not isinstance(multiplier, float):
                # defines depth below ground to check
                depths = ground_level - np.linspace(start=top, stop=bottom, num=100)
                # check if positive real float is returned
                for depth in depths:
                    result = multiplier(depth)
                    if not isinstance(result, float):
                        TypeError(
                            f"One or more results of the {type}-multiplier callable is not a float"
                        )
                        return None
                    else:
                        if type in ["p", "m"]:
                            if result < 0.0:
                                print(
                                    f"One or more results of the {type}-multiplier callable is negative"
                                )
                                return None
                        elif type in ["y", "t"]:
                            if not result > 0.0:
                                ValueError(
                                    f"One or more results of the {type}-multiplier callable is not strictly positive"
                                )
                                return None

        for layer in self.layers:
            if layer.lateral_model is not None:
                # check p-multipliers
                check_multipliers_callable(
                    layer.lateral_model.p_multiplier,
                    self.top_elevation,
                    layer.top,
                    layer.bottom,
                    "p",
                )
                # check y-multipliers
                check_multipliers_callable(
                    layer.lateral_model.y_multiplier,
                    self.top_elevation,
                    layer.top,
                    layer.bottom,
                    "y",
                )
                # check m-multipliers
                check_multipliers_callable(
                    layer.lateral_model.m_multiplier,
                    self.top_elevation,
                    layer.top,
                    layer.bottom,
                    "m",
                )
                # check t-multipliers
                check_multipliers_callable(
                    layer.lateral_model.t_multiplier,
                    self.top_elevation,
                    layer.top,
                    layer.bottom,
                    "t",
                )

        return self


    def __str__(self):
        """List all layers in table-like format"""
        out = ""
        i = 0
        for layer in self.layers:
            i += 1
            out += f"Layer {i}\n" + "-" * 30 + "\n"
            out += f"{layer}\n" + "~" * 30 + "\n"
        return out

    @property
    def bottom_elevation(self) -> float:
        """
        Bottom elevation of the soil profile [m VREF].
        """
        return self.top_elevation - sum([abs(x.top - x.bottom) for x in self.layers])

    def plot(self, assign=False):
        """Creates a plot illustrating the stratigraphy.

        Parameters
        ----------
        assign : bool, optional
            this parameter can be set to True to return the figure, by default False

        Returns
        -------
        matplotlib.pyplot.figure
            only return the object if assign=True

        Example
        -------

        .. image:: _static/plots/SoilProfile_plot.png
           :scale: 70%
        """
        fig = graphics.soil_plot(self)
        return fig if assign is True else None


class Model(AbstractModel):
    """
    A class to create a Model.

    A Model is constructed based on the pile geometry/data primarily.
    Additionally, a soil profile can be fed to the Model, and soil springs can be created.

    Parameters
    ----------
    name : str
        Name of the model
    pile : Pile
        Pile instance to be included in the model.
    soil : Optional[SoilProfile], optional
        SoilProfile instance, by default None.
    element_type : str, optional
        can be of ['EulerBernoulli','Timoshenko'], by default 'Timoshenko'.
    x2mesh : List[float], optional
        additional elevations to be included in the mesh, by default none.
    coarseness : float, optional
        maximum distance in meters between two nodes of the mesh, by default 0.5.
    distributed_lateral : bool, optional
        include distributed lateral springs, by default True.
    distributed_moment : bool, optional
        include distributed moment springs, by default False.
    base_shear : bool, optional
        include lateral spring at pile toe, by default False.
    base_moment : bool, optional
        include moment spring at pile toe, by default False.


    Example
    -------

    >>> from openpile.construct import Pile, Model, Layer
    >>> from openpile.soilmodels import API_sand
    >>> # create pile
    ... p = Pile(name = "WTG01",
    ... 		kind='Circular',
    ... 		material='Steel',
    ... 		top_elevation = 0,
    ... 		pile_sections={
    ... 			'length':[10,30],
    ... 			'diameter':[7.5,7.5],
    ... 			'wall thickness':[0.07, 0.08],
    ... 		}
    ... 	)
    >>> # Create Soil Profile
    >>> sp = SoilProfile(
    ... 	name="BH01",
    ... 	top_elevation=0,
    ... 	water_line=0,
    ... 	layers=[
    ... 		Layer(
    ... 			name='Layer0',
    ... 			top=0,
    ... 			bottom=-40,
    ... 			weight=18,
    ... 			lateral_model= API_sand(phi=30, kind='cyclic')
    ... 		),
    ... 	]
    ... )
    >>> # Create Model
    >>> M = Model(name="Example", pile=p, soil=sp)
    >>> # create Model without soil maximum 5 metres apart.
    >>> Model_without_soil = Model(name = "Example without soil", pile=p, coarseness=5)
    >>> # create Model with nodes maximum 1 metre apart with soil profile
    >>> Model_with_soil = Model(name = "Example with soil", pile=p, soil=sp, coarseness=1)
    """

    #: model name
    name: str
    #: pile instance that the Model should consider
    pile: Pile
    #: soil profile instance that the Model should consider
    soil: Optional[SoilProfile] = None
    #: type of beam elements
    element_type: Literal["Timoshenko", "EulerBernoulli"] = "Timoshenko"
    #: x coordinates values to mesh as nodes
    x2mesh: List[float] = Field(default_factory=list)
    #: mesh coarseness, represent the maximum accepted length of elements
    coarseness: float = 0.5
    #: whether to include p-y springs in the calculations
    distributed_lateral: bool = True
    #: whether to include m-t springs in the calculations
    distributed_moment: bool = True
    #: whether to include Hb-y spring in the calculations
    base_shear: bool = True
    #: whether to include Mb-t spring in the calculations
    base_moment: bool = True
    #: whether to include t-z springs in the calculations
    distributed_axial: bool = False
    #: whether to include Q-z spring in the calculations
    base_axial: bool = False

    @model_validator(mode="after")
    def soil_and_pile_bottom_elevation_match(self):  # pylint: disable=no-self-argument
        if self.soil is None:
            pass
        else:
            if self.pile.bottom_elevation < self.soil.bottom_elevation:
                raise ValueError("The pile ends deeper than the soil profile.")
        return self

    def model_post_init(self,*args,**kwargs):
        
        def create_springs() -> np.ndarray:
            # dim of springs
            spring_dim = 15

            # Allocate array
            py = np.zeros(shape=(self.element_number, 2, 2, spring_dim), dtype=np.float32)
            mt = np.zeros(
                shape=(self.element_number, 2, 2, spring_dim, spring_dim), dtype=np.float32
            )
            Hb = np.zeros(shape=(1, 1, 2, spring_dim), dtype=np.float32)
            Mb = np.zeros(shape=(1, 1, 2, spring_dim), dtype=np.float32)

            # allocate array for axial springs
            tz = np.zeros(shape=(self.element_number, 2, 2, 15), dtype=np.float32)

            # fill in spring for each element
            for layer in self.soil.layers:
                elements_for_layer = self.soil_properties.loc[
                    (self.soil_properties["x_top [m]"] <= layer.top)
                    & (self.soil_properties["x_bottom [m]"] >= layer.bottom)
                ].index

                # py curve
                if layer.lateral_model is None:
                    pass
                else:
                    # Set local layer parameters for each element of the layer
                    for i in elements_for_layer:
                        # vertical effective stress
                        sig_v = self.soil_properties[
                            ["sigma_v top [kPa]", "sigma_v bottom [kPa]"]
                        ].iloc[i]
                        # elevation
                        elevation = self.soil_properties[["x_top [m]", "x_bottom [m]"]].iloc[i]
                        # depth from ground
                        depth_from_ground = (
                            self.soil_properties[["xg_top [m]", "xg_bottom [m]"]].iloc[i]
                        ).abs()
                        # pile width
                        pile_width = self.element_properties["Diameter [m]"].iloc[i]

                        # p-y curves
                        if (
                            layer.lateral_model.spring_signature[0] and self.distributed_lateral
                        ):  # True if py spring function exist

                            # calculate springs (top and) for each element
                            for j in [0, 1]:
                                (py[i, j, 1], py[i, j, 0]) = layer.lateral_model.py_spring_fct(
                                    sig=sig_v[j],
                                    X=depth_from_ground[j],
                                    layer_height=(layer.top - layer.bottom),
                                    depth_from_top_of_layer=(layer.top - elevation[j]),
                                    D=pile_width,
                                    L=(self.soil.top_elevation - self.pile.bottom_elevation),
                                    below_water_table=elevation[j] <= self.soil.water_line,
                                    output_length=spring_dim,
                                )

                        # # t-z curves
                        # if (
                        #     layer.axial_model is not None
                        # ):  # True if tz spring function exist

                        #     # calculate springs (top and bottom) for each element
                        #     for j in [0, 1]:
                        #         (tz[i, j, 1], tz[i, j, 0]) = layer.axial_model.tz_spring_fct(
                        #             sig=sig_v[j],
                        #             X=depth_from_ground[j],
                        #             layer_height=(layer.top - layer.bottom),
                        #             depth_from_top_of_layer=(layer.top - elevation[j]),
                        #             D=pile_width,
                        #             L=(self.soil.top_elevation - self.pile.bottom_elevation),
                        #             below_water_table=elevation[j] <= self.soil.water_line,
                        #             output_length=spring_dim,
                        #         )

                        if (
                            layer.lateral_model.spring_signature[2] and self.distributed_moment
                        ):  # True if mt spring function exist

                            # calculate springs (top and) for each element
                            for j in [0, 1]:
                                (mt[i, j, 1], mt[i, j, 0]) = layer.lateral_model.mt_spring_fct(
                                    sig=sig_v[j],
                                    X=depth_from_ground[j],
                                    layer_height=(layer.top - layer.bottom),
                                    depth_from_top_of_layer=(layer.top - elevation[j]),
                                    D=pile_width,
                                    L=(self.soil.top_elevation - self.pile.bottom_elevation),
                                    below_water_table=elevation[j] <= self.soil.water_line,
                                    output_length=spring_dim,
                                )

                    # check if pile tip is within layer
                    if (
                        layer.top >= self.pile.bottom_elevation
                        and layer.bottom <= self.pile.bottom_elevation
                    ):

                        # Hb curve
                        sig_v_tip = self.soil_properties["sigma_v bottom [kPa]"].iloc[-1]

                        if layer.lateral_model.spring_signature[1] and self.base_shear:

                            # calculate Hb spring
                            (Hb[0, 0, 1], Hb[0, 0, 0]) = layer.lateral_model.Hb_spring_fct(
                                sig=sig_v_tip,
                                X=(self.soil.top_elevation - self.soil.bottom_elevation),
                                layer_height=(layer.top - layer.bottom),
                                depth_from_top_of_layer=(layer.top - self.pile.bottom_elevation),
                                D=pile_width,
                                L=(self.soil.top_elevation - self.pile.bottom_elevation),
                                below_water_table=self.pile.bottom_elevation
                                <= self.soil.water_line,
                                output_length=spring_dim,
                            )

                        # Mb curve
                        if layer.lateral_model.spring_signature[3] and self.base_moment:

                            (Mb[0, 0, 1], Mb[0, 0, 0]) = layer.lateral_model.Mb_spring_fct(
                                sig=sig_v_tip,
                                X=(self.soil.top_elevation - self.soil.bottom_elevation),
                                layer_height=(layer.top - layer.bottom),
                                depth_from_top_of_layer=(layer.top - self.pile.bottom_elevation),
                                D=pile_width,
                                L=(self.soil.top_elevation - self.pile.bottom_elevation),
                                below_water_table=self.pile.bottom_elevation
                                <= self.soil.water_line,
                                output_length=spring_dim,
                            )

            if check_springs(py):
                print("py springs have negative or NaN values.")
                print(
                    """if using PISA type springs, this can be due to parameters behind out of the parameter space.
                Please check that: 2 < L/D < 6.
                """
                )
            if check_springs(mt):
                print("mt springs have negative or NaN values.")
                print(
                    """if using PISA type springs, this can be due to parameters behind out of the parameter space.
                Please check that: 2 < L/D < 6.
                """
                )
            if check_springs(Hb):
                print("Hb spring has negative or NaN values.")
                print(
                    """if using PISA type springs, this can be due to parameters behind out of the parameter space.
                Please check that: 2 < L/D < 6.
                """
                )
            if check_springs(Mb):
                print("Mb spring has negative or NaN values.")
                print(
                    """if using PISA type springs, this can be due to parameters behind out of the parameter space.
                Please check that: 2 < L/D < 6.
                """
                )
            return py, mt, Hb, Mb, tz

        self.soil_properties, self.element_properties, self.nodes_coordinates, self.element_coordinates =  _model_build.get_all_properties(self.pile, self.soil,self.x2mesh, self.coarseness)
        self.element_number = int(self.element_properties.shape[0])

        # Create arrays of springs
        (
            self._py_springs,
            self._mt_springs,
            self._Hb_spring,
            self._Mb_spring,
            self._tz_springs,
        ) = create_springs()

        # Initialise nodal global forces with link to nodes_coordinates (used for force-driven calcs)
        self.global_forces = self.nodes_coordinates.copy()
        self.global_forces["Px [kN]"] = 0
        self.global_forces["Py [kN]"] = 0
        self.global_forces["Mz [kNm]"] = 0

        # Initialise nodal global displacement with link to nodes_coordinates (used for displacement-driven calcs)
        self.global_disp = self.nodes_coordinates.copy()
        self.global_disp["Tx [m]"] = 0
        self.global_disp["Ty [m]"] = 0
        self.global_disp["Rz [rad]"] = 0

        # Initialise nodal global support with link to nodes_coordinates (used for defining boundary conditions)
        self.global_restrained = self.nodes_coordinates.copy()
        self.global_restrained["Tx"] = False
        self.global_restrained["Ty"] = False
        self.global_restrained["Rz"] = False

    @property
    def embedment(self) -> float:
        """Pile embedment length [m].

        Returns
        -------
        float (or None if no SoilProfile is present)
            Pile embedment
        """
        if self.soil is None:
            return None
        else:
            return self.soil.top_elevation - self.pile.bottom_elevation

    @property
    def top(self) -> float:
        """top elevation of the model [m].

        Returns
        -------
        float
        """
        if self.soil is None:
            return self.pile.top_elevation
        else:
            return max(self.pile.top_elevation, self.soil.top_elevation, self.soil.water_line)

    @property
    def bottom(self) -> float:
        """bottom elevation of the model [m].

        Returns
        -------
        float
        """

        if self.soil is None:
            return self.pile.bottom_elevation
        else:
            return min(self.pile.bottom_elevation, self.soil.bottom_elevation)

    def get_structural_properties(self) -> pd.DataFrame:
        """
        Returns a table with the structural properties of the pile sections.
        """
        try:
            return self.element_properties
        except AttributeError:
            print("Data not found. Please create Model with the Model.create() method.")
        except Exception as e:
            print(e)

    def get_soil_properties(self) -> pd.DataFrame:
        """
        Returns a table with the soil main properties and soil models of each element.
        """
        try:
            return self.soil_properties
        except AttributeError:
            print("Data not found. Please create Model with the Model.create() method.")
        except Exception as e:
            print(e)

    def get_pointload(self, output=False, verbose=True):
        """
        Returns the point loads currently defined in the mesh via printout statements.

        Parameters
        ----------
        output : bool, optional
            If true, it returns the printout statements as a variable, by default False.
        verbose : float, optional
            if True, printout statements printed automaically (ideal for use with iPython), by default True.
        """
        out = ""
        try:
            for idx, elevation, _, Px, Py, Mz in self.global_forces.itertuples(name=None):
                if any([Px, Py, Mz]):
                    string = f"\nLoad applied at elevation {elevation} m (node no. {idx}): Px = {Px} kN, Py = {Py} kN, Mx = {Mz} kNm."
                    if verbose is True:
                        print(string)
                    out += f"\nLoad applied at elevation {elevation} m (node no. {idx}): Px = {Px} kN, Py = {Py} kN, Mx = {Mz} kNm."
            if output is True:
                return out
        except Exception:
            print("No data found. Please create the Model first.")
            raise

    def set_pointload(
        self,
        elevation: float = 0.0,
        Py: float = None,
        Px: float = None,
        Mz: float = None,
    ):
        """
        Defines the point load(s) at a given elevation.

        .. note:
            If run several times at the same elevation, the loads are overwritten by the last command.


        Parameters
        ----------
        elevation : float, optional
            the elevation must match the elevation of a node, by default 0.0.
        Py : float, optional
            Shear force in kN, by default None.
        Px : float, optional
            Normal force in kN, by default None.
        Mz : float, optional
            Bending moment in kNm, by default None.
        """

        # identify if one node is at given elevation or if load needs to be split
        nodes_elevations = self.nodes_coordinates["x [m]"].values
        # check if corresponding node exist
        check = np.isclose(nodes_elevations, np.tile(elevation, nodes_elevations.shape), atol=0.001)

        try:
            if any(check):
                # one node correspond, extract node
                node_idx = int(np.where(check == True)[0])
                # apply loads at this node
                if Px is not None:
                    self.global_forces.loc[node_idx, "Px [kN]"] = Px
                if Py is not None:
                    self.global_forces.loc[node_idx, "Py [kN]"] = Py
                if Mz is not None:
                    self.global_forces.loc[node_idx, "Mz [kNm]"] = Mz
            else:
                if (
                    elevation > self.nodes_coordinates["x [m]"].iloc[0]
                    or elevation < self.nodes_coordinates["x [m]"].iloc[-1]
                ):
                    print(
                        "Load not applied! The chosen elevation is outside the mesh. The load must be applied on the structure."
                    )
                else:
                    print(
                        "Load not applied! The chosen elevation is not meshed as a node. Please include elevation in `x2mesh` variable when creating the Model."
                    )
        except Exception:
            print("\n!User Input Error! Please create Model first with the Model.create().\n")
            raise

    def set_pointdisplacement(
        self,
        elevation: float = 0.0,
        Ty: float = None,
        Tx: float = None,
        Rz: float = None,
    ):
        """
        Defines the displacement at a given elevation.

        .. note::
            for defining supports, this function should not be used, rather use `.set_support()`.

        Parameters
        ----------
        elevation : float, optional
            the elevation must match the elevation of a node, by default 0.0.
        Ty : float, optional
            Translation along y-axis, by default None.
        Tx : float, optional
            Translation along x-axis, by default None.
        Rz : float, optional
            Rotation around z-axis, by default None.
        """

        try:
            # identify if one node is at given elevation or if load needs to be split
            nodes_elevations = self.nodes_coordinates["x [m]"].values
            # check if corresponding node exist
            check = np.isclose(
                nodes_elevations, np.tile(elevation, nodes_elevations.shape), atol=0.001
            )

            if any(check):
                # one node correspond, extract node
                node_idx = int(np.where(check == True)[0])
                # apply displacements at this node
                if Tx is not None:
                    self.global_disp.loc[node_idx, "Tx [m]"] = Tx
                    self.global_restrained.loc[node_idx, "Tx"] = Tx > 0.0
                if Ty is not None:
                    self.global_disp.loc[node_idx, "Ty [m]"] = Ty
                    self.global_restrained.loc[node_idx, "Ty"] = Ty > 0.0
                if Rz is not None:
                    self.global_disp.loc[node_idx, "Rz [rad]"] = Rz
                    self.global_restrained.loc[node_idx, "Rz"] = Rz > 0.0
                # set restrain at this node

            else:
                if (
                    elevation > self.nodes_coordinates["x [m]"].iloc[0]
                    or elevation < self.nodes_coordinates["x [m]"].iloc[-1]
                ):
                    print(
                        "Support not applied! The chosen elevation is outside the mesh. The support must be applied on the structure."
                    )
                else:
                    print(
                        "Support not applied! The chosen elevation is not meshed as a node. Please include elevation in `x2mesh` variable when creating the Model."
                    )
        except Exception:
            print("\n!User Input Error! Please create Model first with the Model.create().\n")
            raise

    def set_support(
        self,
        elevation: float = 0.0,
        Ty: bool = False,
        Tx: bool = False,
        Rz: bool = False,
    ):
        """
        Defines the supports at a given elevation. If True, the relevant degree of freedom is restrained.

        .. note:
            If run several times at the same elevation, the support are overwritten by the last command.


        Parameters
        ----------
        elevation : float, optional
            the elevation must match the elevation of a node, by default 0.0.
        Ty : bool, optional
            Translation along y-axis, by default False.
        Tx : bool, optional
            Translation along x-axis, by default False.
        Rz : bool, optional
            Rotation around z-axis, by default False.
        """

        try:
            # identify if one node is at given elevation or if load needs to be split
            nodes_elevations = self.nodes_coordinates["x [m]"].values
            # check if corresponding node exist
            check = np.isclose(
                nodes_elevations, np.tile(elevation, nodes_elevations.shape), atol=0.001
            )

            if any(check):
                # one node correspond, extract node
                node_idx = int(np.where(check == True)[0])
                # apply loads at this node
                self.global_restrained.loc[node_idx, "Tx"] = Tx
                self.global_restrained.loc[node_idx, "Ty"] = Ty
                self.global_restrained.loc[node_idx, "Rz"] = Rz
            else:
                if (
                    elevation > self.nodes_coordinates["x [m]"].iloc[0]
                    or elevation < self.nodes_coordinates["x [m]"].iloc[-1]
                ):
                    print(
                        "Support not applied! The chosen elevation is outside the mesh. The support must be applied on the structure."
                    )
                else:
                    print(
                        "Support not applied! The chosen elevation is not meshed as a node. Please include elevation in `x2mesh` variable when creating the Model."
                    )
        except Exception:
            print("\n!User Input Error! Please create Model first with the Model.create().\n")
            raise

    def get_py_springs(self, kind: str = "node") -> pd.DataFrame:
        """Table with p-y springs computed for the given Model.

        Posible to extract the springs at the node level (i.e. spring at each node)
        or element level (i.e. top and bottom springs at each element)

        Parameters
        ----------
        kind : str
            can be of ("node", "element").

        Returns
        -------
        pd.DataFrame (or None if no SoilProfile is present)
            Table with p-y springs, i.e. p-value [kN/m] and y-value [m].
        """
        if self.soil is None:
            return None
        else:
            if kind == "element":
                return misc.get_full_springs(
                    springs=self._py_springs,
                    elevations=self.nodes_coordinates["x [m]"].values,
                    kind="p-y",
                )
            elif kind == "node":
                return misc.get_reduced_springs(
                    springs=self._py_springs,
                    elevations=self.nodes_coordinates["x [m]"].values,
                    kind="p-y",
                )
            else:
                return None

    def get_mt_springs(self, kind: str = "node") -> pd.DataFrame:
        """Table with m-t (rotational) springs computed for the given Model.

        Posible to extract the springs at the node level (i.e. spring at each node)
        or element level (i.e. top and bottom springs at each element)

        Parameters
        ----------
        kind : str
            can be of ("node", "element").

        Returns
        -------
        pd.DataFrame (or None if no SoilProfile is present)
            Table with m-t springs, i.e. m-value [kNm] and t-value [-].
        """
        if self.soil is None:
            return None
        else:
            if kind == "element":
                return misc.get_full_springs(
                    springs=self._mt_springs,
                    elevations=self.nodes_coordinates["x [m]"].values,
                    kind="m-t",
                )
            elif kind == "node":
                return misc.get_reduced_springs(
                    springs=self._mt_springs,
                    elevations=self.nodes_coordinates["x [m]"].values,
                    kind="m-t",
                )
            else:
                return None

    def get_Hb_spring(self) -> pd.DataFrame:
        """Table with Hb (base shear) spring computed for the given Model.


        Returns
        -------
        pd.DataFrame (or None if no SoilProfile is present)
            Table with Hb spring, i.e. H-value [kN] and y-value [m].
        """
        if self.soil is None:
            return None
        else:
            spring_dim = self._Hb_spring.shape[-1]

            column_values_spring = [f"VAL {i}" for i in range(spring_dim)]

            df = pd.DataFrame(
                data={
                    "Node no.": [self.element_number + 1] * 2,
                    "Elevation [m]": [self.pile.bottom_elevation] * 2,
                }
            )
            df["type"] = ["Hb", "y"]
            df[column_values_spring] = self._Hb_spring.reshape(2, spring_dim)

            return df

    def get_Mb_spring(self) -> pd.DataFrame:
        """Table with Mb (base moment) spring computed for the given Model.


        Returns
        -------
        pd.DataFrame (or None if no SoilProfile is present)
            Table with Mb spring, i.e. M-value [kNn] and t-value [-].
        """
        if self.soil is None:
            return None
        else:
            spring_dim = self._Hb_spring.shape[-1]

            column_values_spring = [f"VAL {i}" for i in range(spring_dim)]

            df = pd.DataFrame(
                data={
                    "Node no.": [self.element_number + 1] * 2,
                    "Elevation [m]": [self.pile.bottom_elevation] * 2,
                }
            )
            df["type"] = ["Mb", "t"]
            df[column_values_spring] = self._Hb_spring.reshape(2, spring_dim)

            return df

    def plot(self, assign=False):
        """Create a plot of the model with the mesh and boundary conditions.

        Parameters
        ----------
        assign : bool, optional
            this parameter can be set to True to return the figure, by default False.

        Returns
        -------
        matplotlib.pyplot.figure
            only return the object if assign=True.

        Examples
        --------

        *Plot without SoilProfile fed to the model:*

        .. image:: _static/plots/Model_no_soil_plot.png
           :scale: 70%

        *Plot with SoilProfile fed to the model:*

        .. image:: _static/plots/Model_with_soil_plot.png
           :scale: 70%
        """
        fig = graphics.connectivity_plot(self)
        return fig if assign else None

    @classmethod
    def create(
        cls,
        name: str,
        pile: Pile,
        soil: Optional[SoilProfile] = None,
        element_type: Literal["Timoshenko", "EulerBernoulli"] = "Timoshenko",
        x2mesh: List[float] = Field(default_factory=list),
        coarseness: float = 0.5,
        distributed_lateral: bool = True,
        distributed_moment: bool = True,
        distributed_axial: bool = False,
        base_shear: bool = True,
        base_moment: bool = True,
        base_axial: bool = False,
    ):
        """A method to create the Model.

        Parameters
        ----------
        name : str
            Name of the model
        pile : Pile
            Pile instance to be included in the model
        soil : Optional[SoilProfile], optional
            SoilProfile instance, by default None
        element_type : str, optional
            can be of ['EulerBernoulli','Timoshenko'], by default 'Timoshenko'
        x2mesh : List[float], optional
            additional elevations to be included in the mesh, by default none
        coarseness : float, optional
            maximum distance in meters between two nodes of the mesh, by default 0.5
        distributed_lateral : bool, optional
            include distributed lateral springs, by default True
        distributed_moment : bool, optional
            include distributed moment springs, by default False
        base_shear : bool, optional
            include lateral spring at pile toe, by default False
        base_moment : bool, optional
            include moment spring at pile toe, by default False

        Returns
        -------
        openpile.construct.Model
            a Model instance with a Pile structure and optionally a SoilProfile
        """

        obj = cls(
            name=name,
            pile=pile,
            soil=soil,
            element_type=element_type,
            x2mesh=x2mesh,
            coarseness=coarseness,
            distributed_lateral=distributed_lateral,
            distributed_moment=distributed_moment,
            distributed_axial=distributed_axial,
            base_shear=base_shear,
            base_moment=base_moment,
            base_axial=base_axial,
        )

        warnings.warn(
            "\nThe method Model.create() will be removed in version 1.0.0."
            "\nPlease use the base class to create a Pile instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        return obj

    def __str__(self):
        return self.element_properties.to_string()
