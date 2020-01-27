
##############################################################################
## 21 May 2017
## Authors: Sai Nudurupati & Erkan Istanbulluoglu
## 
## This is to replicate create_fires function from
## Sujith Ravi's model as implemented in resource_redistribution_funcs.py.
## In this fire creation method, we will also consider trees. Also, we
## introduce fire suscessibility thresholds for shrubs and trees.
##############################################################################

# Import Packages
import numpy as np
from landlab import FieldError, Component
from ...utils.decorators import use_file_name_or_kwds
from .funcs import (convert_phy_pft_to_distr_pft,
                    convert_distr_pft_to_phy_pft)

_VALID_SCHEMES = set(["ravi_et_al_2009", "zhou_et_al_2013"])


def _assert_pft_scheme_is_valid(scheme):
    if scheme not in _VALID_SCHEMES:
        raise ValueError("%s: Invalid PFT scheme" % scheme)


# Declare Global Variables (If any)
# 'ravi_et_al_2009' pft_scheme - used internally
BARE = 0
GRASS = 1
SHRUB = 2
BURNTGRASS = 3
BURNTSHRUB = 4
TREE = 5
BURNTTREE = 6
SHRUBSEED = 7
TREESEED = 8


class SpatialDisturbance(Component):
    """
    Landlab component that implements that implements
    spatial disturbances, such as wildfires and
    grazing, conceptualized by Ravi and D'Odorico (2009).
    These disturbances modify the vegetation occupying
    the cells (e.g. convert SHRUB to BURNTSHRUB) depending on
    their spatial reach.
    
    This component is designed to work with two different
    plant functional type (PFT) schemes: 'ravi_et_al_2009',
    and 'zhou_et_al_2013'.
    'ravi_et_al_2009': Each cell in the RasterModelGrid object
    can take an integer from 0 through 8 to
    represent the cell states for bare soil [0],
    grass [1], shrub [2], burnt grass [3], burnt shrub [4],
    tree [5], burnt tree [6], shrub seed [7], and tree seed [8].
    This scheme is an extended version of the PFTs used in 
    Ravi and D'Odorico (2009).
    'zhou_et_al_2013': Each cell in the RasterModelGrid object
    can take an integer from 0 through 5 to
    represent the cell states for grass [0],
    shrub [1], tree [2], bare soil [3], shrub seedling [4],
    and tree seedling [5]. This is the default scheme
    used in the component.

    There are two key process-representing methods in this
    component: graze(), and initiate_fires().
    
    References:
    Ravi, S., & D’Odorico, P. (2009). Post-fire 
    resource redistribution and fertility island dynamics
    in shrub encroached desert grasslands: a modeling approach.
    Landscape Ecology, 24(3), 325-335.
    Zhou, X., Istanbulluoglu, E., & Vivoni, E. R. (2013). Modeling the
    ecohydrological role of aspect controlled radiation on tree grass shrub
    coexistence in a semiarid climate. Water Resources Research,
    49(5), 2872-2895.

    .. codeauthor:: Sai Nudurupati and Erkan Istanbulluoglu

    Examples
    --------
    >>> import numpy as np
    >>> np.random.seed(0)
    >>> from landlab import RasterModelGrid as rmg
    >>> from landlab.components import ResourceRedistribution
    >>> grid = rmg((5, 4), xy_spacing=(0.2, 0.2))
    >>> ResourceRedistribution.name
    'Resource Redistribution'
    >>> sorted(ResourceRedistribution.output_var_names)
    ['soil__resources',
     'vegetation__plant_functional_type']
    >>> sorted(ResourceRedistribution.units)
    [('soil__resources', 'None'),
     ('vegetation__plant_functional_type', 'None')]
    >>> grid.at_cell["vegetation__plant_functional_type"] = (
    ...     np.random.randint(0, 5, size=grid.number_of_cells))
    >>> np.allclose(
    ...    grid.at_cell["vegetation__plant_functional_type"],
    ...    np.array([4, 0, 3, 3, 3, 1]))
    True
    >>> grid.at_cell["soil__resources"] = (
    ...     np.ones(grid.number_of_cells, dtype=float))
    >>> rr = ResourceRedistribution(grid)
    >>> rr.grid.number_of_cell_rows
    3
    >>> rr.grid.number_of_cell_columns
    2
    >>> rr.grid is grid
    True
    >>> (eroded_soil,
    ...  eroded_soil_shrub,
    ...  burnt_shrub,
    ...  burnt_grass,
    ...  bare_cells) = rr.erode()
    >>> np.round(eroded_soil, decimals=2) == 0.16
    True
    >>> burnt_shrub.shape == (1,)
    True
    >>> (burnt_shrubs_neigh,
    ...  exclusive,
    ...  shrub_exclusive,
    ...  grass_exclusive,
    ...  bare_exclusive,
    ...  eroded_soil_part) = rr.deposit(eroded_soil, eroded_soil_shrub)
    >>> np.allclose(burnt_shrubs_neigh, np.array([1, 2, 3, 4, 5]))
    True
    >>> eroded_soil_part == 0
    True
    >>> (resource_adjusted,
    ...  eligible_locs_to_adj_neigh,
    ...  elig_locs,
    ...  sed_to_borrow) = rr.re_adjust_resource()
    >>> resource_adjusted == 0.
    True
    >>> V_age = np.zeros(rr.grid.number_of_cells, dtype=int)
    >>> V_age = rr.initialize_Veg_age(V_age=V_age)
    >>> np.allclose(V_age, np.zeros(rr.grid.number_of_cells, dtype=int))
    True
    >>> (V_age, est_1, est_2, est_3, est_4, est_5) = rr.establish(V_age)
    >>> np.allclose(grid.at_cell["vegetation__plant_functional_type"],
    ...             np.array([4, 1, 3, 3, 3, 1]))
    True
    >>> (V_age, Pmor_age, Pmor_age_ws) = rr.mortality(V_age)
    >>> np.allclose(grid.at_cell["vegetation__plant_functional_type"],
    ...             np.array([4, 1, 0, 0, 0, 1]))
    True
    >>> V_age = rr.update_Veg_age(V_age)
    >>> np.allclose(V_age, np.array([1, 1, 0, 0, 0, 1]))
    True
    """

    _name = "Spatial Disturbance"

    _input_var_names = (
            "vegetation__plant_functional_type",
            )

    _output_var_names = (
            "vegetation__plant_functional_type",
            )

    _var_units = {
            "vegetation__plant_functional_type": "None",
            }

    _var_mapping = {
            "vegetation__plant_functional_type": "cell",
            }

    _var_doc = {
            "vegetation__plant_functional_type":
                "classification of plant type - zhou_et_al_2013 (int)"
                + "grass=0, shrub=1, tree=2, bare=3,"
                + "shrub_seedling=4, tree_seedling=5",
            }

    @use_file_name_or_kwds
    def __init__(
        self,
        grid,
        pft_scheme="zhou_et_al_2013",
        **kwds
    ):
        """
        Parameters:
        ----------
        grid: RasterModelGrid
            grid, Landlab's RasterModelGrid object
        pft_scheme: str
            Vegetation Plant Functional Type (PFT);
            shape = [grid.number_of_cells]
            BARE = 0; GRASS = 1; SHRUB = 2; BURNTGRASS = 3; BURNTSHRUB = 4;
            TREE = 5; BURNTTREE = 6; SHRUBSEED = 7; TREESEED = 8.
        """
        self._pft_scheme = pft_scheme
        _assert_pft_scheme_is_valid(self._pft_scheme)
        super(SpatialDisturbance, self).__init__(grid, **kwds)

        if self._pft_scheme == "zhou_et_al_2013":
            if "vegetation__plant_functional_type" not in self.grid.at_cell:
                raise FieldError("Cellular field of 'Plant Functional Type'" +
                                 " is required!")

    def graze(self, V=None, grazing_pressure=0.01):
        """
        Function to implement grazing
        """
        if self._pft_scheme == "zhou_et_al_2013":
            vegtype = self._grid.at_cell["vegetation__plant_functional_type"]
            V = convert_phy_pft_to_distr_pft(self._grid, vegtype)
        elif self._pft_scheme == "ravi_et_al_2009":
            if V is None:
                raise ValueError("Cellular field of 'Plant Functional Type'" +
                                 " should be provided!")
        grz_prob = (0.6 * grazing_pressure +
                    2 * 0.4 * grazing_pressure * np.random.random_sample())
        grass_cells = np.where(V == 1)[0]
        compute_ = np.random.random(grass_cells.shape)
        grazed_cells = grass_cells[compute_ < grz_prob]
        V[grazed_cells] = 0
        if self._pft_scheme == "zhou_et_al_2013":
            vegtype = convert_distr_pft_to_phy_pft(self._grid, V)
            self._grid.at_cell["vegetation__plant_functional_type"] = vegtype
        return (V, grazed_cells)

    def initiate_fires(
        self,
        V=None,
        n_fires=2,
        fire_area_mean=0.0625,
        fire_area_dev=0.01,
        sh_susc=1.,
        tr_susc=1.,
        gr_susc=1.,
        sh_seed_susc=1.,
        tr_seed_susc=1.,
        gr_vuln=1.,
        sh_vuln=0.,
        sh_seed_vuln=0.,
        tr_vuln=0.,
        tr_seed_vuln=0.,
    ):
        """
        - Add description to this method. If this is the main method or
        one of the main methods, i.e. if this method performs a
        process for which this component is written, make sure you
        mention it.
        - Search for BasicModelInterface (BMI) on CSDMS website.
        We try to follow this interface to enable easier coupling
        with other models.

        Parameters:
        ----------
        grid: RasterModelGrid
            grid, Landlab's RasterModelGrid object
        V: array_like
            Vegetation Plant Functional Type; shape = [grid.number_of_cells]
            BARE = 0; GRASS = 1; SHRUB = 2; BURNTGRASS = 3; BURNTSHRUB = 4;
            TREE = 5; BURNTTREE = 6; SHRUBSEED = 7; TREESEED = 8
        n_fires: int, optional
            Number of fires to be created
        fire_area_mean: float, optional
            mean area of uniform distribution to sample fire size
        fire_area_dev: float, optional
            standard deviation of uniform distribution to sample fire size
        sh_susc: float, optional
            susceptibility of SHRUB to fire
        tr_susc: float, optional
            susceptibility of TREE to fire
        gr_susc: float, optional
            susceptibility of GRASS to fire
        sh_seed_susc: float, optional
            susceptibility of SHRUBSEED to fire
        tr_seed_susc: float, optional
            susceptibility of TREESEED to fire
        gr_vuln: float, optional
            probability of GRASS cell to catch fire due to
            lightning
        sh_vuln: float, optional
            probability of SHRUB cell to catch fire due to
            lightning
        sh_seed_vuln: float, optional
            probability of SHRUBSEED cell to catch fire due to
            lightning
        tr_vuln: float, optional
            probability of TREE cell to catch fire due to
            lightning
        tr_seed_vuln: float, optional
            probability of TREESEED cell to catch fire due to
            lightning
        """
        if self._pft_scheme == "zhou_et_al_2013":
            vegtype = self._grid.at_cell["vegetation__plant_functional_type"]
            V = convert_phy_pft_to_distr_pft(self._grid, vegtype)
        elif self._pft_scheme == "ravi_et_al_2009":
            if V is None:
                raise ValueError("Cellular field of 'Plant Functional Type'" +
                                 " should be provided!")
        susc = self._set_susceptibility(
                V,
                sh_susc=sh_susc,
                tr_susc=tr_susc,
                gr_susc=gr_susc,
                sh_seed_susc=sh_seed_susc,
                tr_seed_susc=tr_seed_susc
        )
        ignition_cells = []
        burnt_locs = []  # Total burnt locations for all fires
        for i in range(0, n_fires):
            ignition_cell = np.random.choice(self._grid.number_of_cells, 1)
            if self._is_cell_ignitable(
                    V,
                    ignition_cell,
                    gr_vuln=gr_vuln,
                    sh_vuln=sh_vuln,
                    sh_seed_vuln=sh_seed_vuln,
                    tr_vuln=tr_vuln,
                    tr_seed_vuln=tr_seed_vuln
            ):
                (fire_locs, V) = self._spread_fire(
                                      V,
                                      ignition_cell,
                                      fire_area_mean=fire_area_mean,
                                      fire_area_dev=fire_area_dev,
                                      susc=susc
                )
            else:
                fire_locs = []
            burnt_locs += fire_locs
            ignition_cells += list(ignition_cell)

        if self._pft_scheme == "zhou_et_al_2013":
            vegtype = convert_distr_pft_to_phy_pft(self._grid, V)
            self._grid.at_cell["vegetation__plant_functional_type"] = vegtype
        return (V, burnt_locs, ignition_cells)

    def _spread_fire(
        self,
        V,
        ignition_cell,
        fire_area_mean=0.0625,
        fire_area_dev=0.01,
        susc=None
    ):
        """
        - An underscore in the front signals the user to stay away
        from using this method (is intended for internal use).
        - Works just like a regular method but implies a hidden method.
        - You should still document these methods though.

        Parameters:
        ----------
        grid: RasterModelGrid
            grid, Landlab's RasterModelGrid object
        V: array_like
            Vegetation Plant Functional Type; shape = [grid.number_of_cells]
            BARE = 0; GRASS = 1; SHRUB = 2; BURNTGRASS = 3; BURNTSHRUB = 4;
            TREE = 5; BURNTTREE = 6; SHRUBSEED = 7; TREESEED = 8
        ignition_cell: int
            cell id where the fire starts
        fire_area_mean: float, optional
            mean area of uniform distribution to sample fire size
        fire_area_dev: float, optional
            standard deviation of uniform distribution to sample fire size
        sh_susc: float, optional
            susceptibility of shrubs to burn
        tr_susc: float, optional
            susceptibility of trees to burn
        gr_susc: float, optional
            susceptibility of grass to burn
        sh_seed_susc: float, optional
            susceptibility of shrub seedlings to burn
        tr_seed_susc: float, optional
            susceptibility of tree seedlings to burn
        """
        if susc == None:
            susc = np.ones(self.grid.number_of_cells)
        fire_burnt = 0    # To check how many cells are being burnt
        grass_cells = np.where(V == GRASS)[0]
        if int(grass_cells.shape[0]) == 1:
            return [], V, []
        fire_locs = []       # record all the cell ids where fire has spread
        fire_locs += list(ignition_cell)
        burning_cells = [ignition_cell]
        V = self._burn_veg(V, burning_cells)
        fire_burnt += 1
        alr_cntd = []
        # loop to propagate fires one ring at a time
        while (burning_cells != []):
            newly_burnt = []   # Cells to be burnt in the sub-loop
            for cell in burning_cells:
                neigh_ = self._grid.looped_neighbors_at_cell[cell]
                veg_neighbors = (neigh_[np.where(V[neigh_] != BARE)])
                unique_neigh = np.setdiff1d(veg_neighbors, alr_cntd)
                alr_cntd += list(unique_neigh)
                susc_neigh = self._check_susc(unique_neigh,
                                              susc[unique_neigh])
                newly_burnt += (susc_neigh)
            if newly_burnt == []:
                break
            burning_cells = np.unique(np.array(newly_burnt))
            fire_locs += list(burning_cells)
            V = self._burn_veg(V, burning_cells)
            fire_burnt += int(burning_cells.shape[0])
            fire_area_sample = (self._fetch_uniform_random_fire_area(
                                        fire_area_mean, fire_area_dev))
            if fire_burnt > fire_area_sample*self._grid.number_of_cells:
                break
        return (fire_locs, V)

    def _fetch_uniform_random_fire_area(self, fire_area_mean, fire_area_dev):
        a = fire_area_mean - fire_area_dev
        return (a+2*fire_area_dev*np.random.random_sample())

    def _burn_veg(self, V, newly_burnt):
        newly_burnt = np.array(newly_burnt, dtype=int)
        burnt_grass = newly_burnt[np.where(V[newly_burnt] == GRASS)[0]]
        burnt_shrub = newly_burnt[np.where(V[newly_burnt] == SHRUB)[0]]
        burnt_tree = newly_burnt[np.where(V[newly_burnt] == TREE)[0]]
        burnt_shrub_seed = newly_burnt[np.where(
                                        V[newly_burnt] == SHRUBSEED)[0]]
        burnt_tree_seed = newly_burnt[np.where(V[newly_burnt] == TREESEED)[0]]
        V[burnt_grass] = BURNTGRASS
        V[burnt_shrub] = BURNTSHRUB
        V[burnt_tree] = BURNTTREE
        V[burnt_shrub_seed] = BURNTSHRUB
        V[burnt_tree_seed] = BURNTTREE
        return (V)

    def _check_susc(self, some_neighbors, susc):
        if some_neighbors.shape[0] == 0:
            susc_neighbors = []
        else:
            rand_val = np.random.rand(some_neighbors.shape[0])
            susc_neighbors = some_neighbors[rand_val < susc]
        return (list(susc_neighbors))

    def _set_susceptibility(
        self,
        V=None,
        sh_susc=1.,
        tr_susc=1.,
        gr_susc=1.,
        sh_seed_susc=1.,
        tr_seed_susc=1.
    ):
        susc = np.zeros(self.grid.number_of_cells)
        susc[V==SHRUB] = sh_susc
        susc[V==TREE] = tr_susc
        susc[V==GRASS] = gr_susc
        susc[V==SHRUBSEED] = sh_seed_susc
        susc[V==TREESEED] = tr_seed_susc
        return susc

    def _is_cell_ignitable(
        self,
        V,
        ignition_cell,
        gr_vuln=1.,
        sh_vuln=0.,
        sh_seed_vuln=0.,
        tr_vuln=0.,
        tr_seed_vuln=0.
    ):
        vulnerability = np.choose(
            V[ignition_cell],
            [0.,
             gr_vuln,
             sh_vuln,
             0.,
             0.,
             tr_vuln, 0.,
             sh_seed_vuln,
             tr_seed_vuln]
        ) 
        rand_val = np.random.rand()
        if rand_val < vulnerability:
            return True
        else:
            return False